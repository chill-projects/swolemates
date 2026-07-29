import createClient from "openapi-fetch";

import type { paths } from "./generated";

/**
 * The typed REST client. Paths, request bodies and responses all come from the backend's
 * OpenAPI schema via `make types`, so a backend change that breaks the frontend fails
 * typecheck instead of failing at runtime.
 *
 * Same-origin in production; Vite proxies /api to :8000 in dev.
 */
export const api = createClient<paths>({ baseUrl: "/" });
