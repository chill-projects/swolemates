import createClient from "openapi-fetch";

import { clearSession, getToken, refreshSession } from "../auth/authkit";
import type { paths } from "./generated";

/**
 * The typed REST client. Paths, request bodies and responses all come from the backend's
 * OpenAPI schema via `make types`, so a backend change that breaks the frontend fails
 * typecheck instead of failing at runtime.
 *
 * Same-origin in production; Vite proxies /api to :8000 in dev.
 */
export const api = createClient<paths>({ baseUrl: "/" });

api.use({
  onRequest({ request }) {
    const token = getToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  async onResponse({ response }) {
    // A 401 doesn't necessarily mean the session is over — the proactive refresh timer
    // in authkit.ts should normally beat expiry, but a backgrounded/sleeping tab can
    // still land here with a dead access token and a perfectly good refresh token. Try
    // to recover before giving up on the session; only a rejected refresh means the
    // user is actually signed out.
    if (response.status === 401) {
      const recovered = await refreshSession();
      if (!recovered) clearSession();
    }
    return response;
  },
});
