import createClient from "openapi-fetch";

import { clearToken, getToken } from "../auth/authkit";
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
  onResponse({ response }) {
    // An expired or rejected token should drop us back to signed-out rather than
    // leaving a dead token in place to fail every subsequent request.
    if (response.status === 401) clearToken();
    return response;
  },
});
