import createClient from "openapi-fetch";

import { getToken, isTokenFresh, refreshSession } from "../auth/authkit";
import type { paths } from "./generated";

/**
 * The typed REST client. Paths, request bodies and responses all come from the backend's
 * OpenAPI schema via `make types`, so a backend change that breaks the frontend fails
 * typecheck instead of failing at runtime.
 *
 * Same-origin in production; Vite proxies /api to :8000 in dev.
 */
export const api = createClient<paths>({ baseUrl: "/" });

// One retry per request, keyed by a header the server ignores — so an endpoint that
// keeps 401ing after a genuine refresh can't spin.
const RETRY_HEADER = "X-Auth-Retried";

api.use({
  async onRequest({ request }) {
    // Just-in-time refresh: if the token is missing or within its expiry buffer,
    // exchange the refresh cookie *before* sending, so expiry never turns into a 401
    // the user can see. Coalesced/locked in authkit, so a burst of requests triggers
    // one refresh. A failed refresh here isn't fatal — send unauthenticated and let
    // onResponse / the shell deal with it.
    let token = getToken();
    if (!isTokenFresh(token)) {
      await refreshSession().catch(() => {});
      token = getToken();
    }
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  async onResponse({ request, response }) {
    if (response.status !== 401 || request.headers.has(RETRY_HEADER)) return response;

    // The token was fresh but the server still rejected it — it's been revoked, or a
    // refresh raced. Try once more.
    const result = await refreshSession();
    if (result !== "ok") {
      // "rejected": performRefresh already tore down local state and the server
      //   cleared its cookie — the caller's 401 will surface as WhoamiError("anonymous").
      // "error": WorkOS blip / misconfig — the session may still be fine, so don't sign
      //   out; surface the 401 and let a later request retry the refresh.
      return response;
    }

    // Refreshed — replay the original request once with the new token. GETs only:
    // re-sending a mutation isn't safe, and the JIT onRequest check makes a mutation
    // 401 vanishingly rare anyway.
    if (request.method !== "GET") return response;
    const retried = new Request(request.url, {
      method: "GET",
      headers: new Headers(request.headers),
      credentials: request.credentials,
    });
    retried.headers.set("Authorization", `Bearer ${getToken() ?? ""}`);
    retried.headers.set(RETRY_HEADER, "1");
    return fetch(retried);
  },
});
