/**
 * AuthKit login for the browser: OAuth 2.1 authorization code + PKCE.
 *
 * Public client, so the login leg has no secret — PKCE is what binds the code to this
 * browser. Two tokens come out of it:
 *
 * - the **access token** (short-lived) lives in `sessionStorage` and dies with the tab;
 *   losing it just costs a refresh round-trip.
 * - the **refresh token** (7 days) is never touched by JS. Right after login the SPA
 *   hands it to `POST /api/auth/session`, which seals it into an httpOnly cookie.
 *   `POST /api/auth/refresh` reads that cookie and exchanges it at the same AuthKit
 *   `/oauth2/token` login used — same public client, no secret — then rotates the
 *   cookie and returns a fresh access token. That leg is server-side to keep the
 *   refresh token out of JS, not because it needs a credential the browser lacks.
 *
 * Refreshing is coordinated three ways so a rotated (single-use) token is never
 * replayed: coalesced within a tab, serialized across tabs via the Web Locks API, and
 * re-checked inside the lock (another tab may have just done it).
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

export interface AuthConfig {
  configured: boolean;
  authkit_domain: string;
  client_id: string;
  redirect_uri: string;
  /** RFC 8707 resource indicator — requested in both OAuth legs so the token's `aud`
   *  matches what the backend validates. */
  resource: string;
  environment: string;
}

const TOKEN_KEY = "swolemates.access_token";
const VERIFIER_KEY = "swolemates.pkce_verifier";

/** Refresh this many ms before the access token actually expires. authkit-nextjs uses
 *  the same margin for ≤5-minute tokens. */
const REFRESH_BUFFER_MS = 30_000;

/** Overshoot the computed wake-up by this much. A timer that fires even a millisecond
 *  early leaves the token still *fresh* by `REFRESH_BUFFER_MS`, so `refreshSession()`
 *  short-circuits on its freshness check and returns "ok" without storing anything —
 *  and since only `storeAccessToken()` re-arms, the chain would die right there. */
const REFRESH_SLOP_MS = 1_000;

/** Backoff for a transient failure. Doubles up to the cap and keeps going: a WorkOS
 *  blip lasting longer than one retry must not end background refresh for the tab. */
const RETRY_BASE_MS = 30_000;
const RETRY_MAX_MS = 300_000;

export type RefreshResult = "ok" | "rejected" | "error";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

/** Reads `exp` out of a JWT without verifying it — we already trust our own token.
 *  Returns null for anything unparseable, which callers treat as "expired". */
function tokenExpiryMs(accessToken: string): number | null {
  const payload = accessToken.split(".")[1];
  if (!payload) return null;
  try {
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))) as {
      exp?: number;
    };
    return typeof json.exp === "number" ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

/** True only if `token` is present and has more than REFRESH_BUFFER_MS of life left.
 *  An undecodable token is never fresh. */
export function isTokenFresh(token: string | null): boolean {
  if (!token) return false;
  const expiresAt = tokenExpiryMs(token);
  return expiresAt !== null && expiresAt - Date.now() > REFRESH_BUFFER_MS;
}

let refreshTimer: ReturnType<typeof setTimeout> | null = null;

function clearRefreshTimer(): void {
  if (refreshTimer !== null) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

/** One link in the refresh chain: wait `delayMs`, refresh, then re-arm from the
 *  outcome. Every branch either re-arms or deliberately stops, so the chain can't be
 *  ended by a no-op refresh or by a second consecutive failure. */
function armRefreshTimer(delayMs: number, retryMs: number): void {
  clearRefreshTimer();
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    void refreshSession().then((result) => {
      if (result === "rejected") return; // signed out — nothing left to refresh.
      if (result === "ok") {
        // Re-arm here rather than relying on storeAccessToken(): a refresh that was a
        // no-op — the token was already fresh, or another tab won the lock and stored
        // it — never calls that, and the chain would stop silently.
        const token = getToken();
        if (token) scheduleRefresh(token);
        return;
      }
      // "error" is transient (WorkOS blip, network). Keep retrying with backoff.
      armRefreshTimer(retryMs, Math.min(retryMs * 2, RETRY_MAX_MS));
    });
  }, delayMs);
}

/** Background refresh a little before expiry, so an idle open tab never has to wait
 *  out a failed request to recover. Just a convenience now — the per-request check in
 *  api/client.ts is what actually guarantees a live token, since browsers throttle
 *  timers in backgrounded tabs. */
function scheduleRefresh(accessToken: string): void {
  clearRefreshTimer();
  const expiresAt = tokenExpiryMs(accessToken);
  if (expiresAt === null) return;
  // The slop also floors the delay at REFRESH_SLOP_MS, so an already-stale token
  // re-arming itself can't spin.
  const delay = Math.max(expiresAt - Date.now() - REFRESH_BUFFER_MS, 0) + REFRESH_SLOP_MS;
  armRefreshTimer(delay, RETRY_BASE_MS);
}

function storeAccessToken(accessToken: string): void {
  sessionStorage.setItem(TOKEN_KEY, accessToken);
  lastRefresh = { result: "ok", at: Date.now() };
  scheduleRefresh(accessToken);
}

/** Local teardown only — no server round-trip. Used when the server has already
 *  invalidated the session (a rejected refresh clears its own cookie). */
function clearLocalAuth(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  clearRefreshTimer();
}

/** Full sign-out: also tells the backend to drop the refresh cookie. */
export function clearSession(): void {
  clearLocalAuth();
  lastRefresh = { result: "rejected", at: Date.now() };
  void fetch("/api/auth/logout", { method: "POST", credentials: "include" }).catch(() => {});
}

// --- refresh coordination --------------------------------------------------------

let refreshInFlight: Promise<RefreshResult> | null = null;
// Remembers the last outcome briefly so a stream of requests while genuinely signed
// out doesn't fire a `/api/auth/refresh` each — they all see the cached "rejected".
let lastRefresh: { result: RefreshResult; at: number } | null = null;
const REJECTION_CACHE_MS = 3_000;

/** The single entry point. Coalesces concurrent callers in this tab, serializes across
 *  tabs (Web Locks), and skips the network entirely if the token is already fresh by
 *  the time we hold the lock. */
export async function refreshSession(): Promise<RefreshResult> {
  if (isTokenFresh(getToken())) return "ok";
  if (lastRefresh?.result === "rejected" && Date.now() - lastRefresh.at < REJECTION_CACHE_MS) {
    return "rejected";
  }
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const locks = navigator.locks;
      if (locks?.request) {
        return await locks.request("swolemates-auth-refresh", async () => {
          if (isTokenFresh(getToken())) return "ok" as const;
          return performRefresh();
        });
      }
      return await performRefresh();
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function performRefresh(): Promise<RefreshResult> {
  let res: Response;
  try {
    res = await fetch("/api/auth/refresh", { method: "POST", credentials: "include" });
  } catch {
    // Network failure, not a rejected token — keep the session and let a later request
    // (or the timer's backoff) try again.
    lastRefresh = { result: "error", at: Date.now() };
    return "error";
  }

  if (res.ok) {
    const body = (await res.json().catch(() => null)) as { access_token?: string } | null;
    if (!body?.access_token) {
      lastRefresh = { result: "error", at: Date.now() };
      return "error";
    }
    storeAccessToken(body.access_token);
    return "ok";
  }

  if (res.status === 401) {
    // Two different things arrive as 401, and only one of them is a credential dying.
    // `no_session`: no cookie was sent, so nothing was rejected — report signed-out so
    // the shell shows sign-in, but leave local state alone rather than tearing down an
    // access token that may still be perfectly good. `session_expired` (or an older
    // backend that sends no `code` at all — the safe default): WorkOS rejected the
    // refresh token and the server already cleared its cookie, so match it locally.
    const body = (await res.json().catch(() => null)) as { code?: string } | null;
    if (body?.code !== "no_session") clearLocalAuth();
    lastRefresh = { result: "rejected", at: Date.now() };
    return "rejected";
  }

  // 500 (client id / AuthKit domain unconfigured) / 502 (WorkOS down) / anything else —
  // transient. The session may well still be valid; don't sign the user out over it.
  lastRefresh = { result: "error", at: Date.now() };
  return "error";
}

// --- startup --------------------------------------------------------------------

/** Called once on app startup. Returns the auth outcome so the shell can tell
 *  "definitely signed out" from "couldn't reach the server". */
export async function bootstrapSession(): Promise<RefreshResult> {
  const token = getToken();
  if (isTokenFresh(token)) {
    scheduleRefresh(token as string);
    return "ok";
  }
  return refreshSession();
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const res = await fetch("/api/auth/config");
  if (!res.ok) throw new Error("Could not read auth configuration");
  return (await res.json()) as AuthConfig;
}

// --- login ---------------------------------------------------------------------

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

async function createPkcePair(): Promise<{ verifier: string; challenge: string }> {
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return { verifier, challenge: base64url(new Uint8Array(digest)) };
}

/** Send the browser to AuthKit's hosted login. */
export async function login(config: AuthConfig): Promise<void> {
  const { verifier, challenge } = await createPkcePair();
  sessionStorage.setItem(VERIFIER_KEY, verifier);

  const url = new URL("/oauth2/authorize", config.authkit_domain);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", config.client_id);
  url.searchParams.set("redirect_uri", config.redirect_uri);
  url.searchParams.set("resource", config.resource);
  // Without this, the code exchange returns only an access token — no refresh token,
  // so the session dies with the tab (a 5-minute access token otherwise).
  url.searchParams.set("scope", "offline_access");
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  window.location.assign(url.toString());
}

export type CallbackResult = "ok" | "restart" | "failed";

/**
 * Complete the flow on /callback: swap the code for a token, then seal the refresh
 * token into the server-side cookie.
 *
 * "restart" means the PKCE verifier is missing — which happens legitimately when the
 * login continued in a different tab (e.g. WorkOS's email-verification link opens a
 * new one). The fix is simply to start the login again: AuthKit already has a session,
 * so the retry round-trips instantly and this tab gets its own code + verifier pair.
 */
export async function completeLogin(config: AuthConfig): Promise<CallbackResult> {
  const params = new URLSearchParams(window.location.search);
  const oauthError = params.get("error");
  if (oauthError) {
    console.error("AuthKit returned an error:", oauthError, params.get("error_description"));
    window.history.replaceState({}, "", "/");
    return "failed";
  }

  const code = params.get("code");
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  if (!code) return "failed";
  if (!verifier) return "restart";

  const res = await fetch(new URL("/oauth2/token", config.authkit_domain).toString(), {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    // `resource` is deliberately absent here: WorkOS binds the resource at the
    // authorize leg and returns invalid_target if the token leg repeats it.
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.client_id,
      redirect_uri: config.redirect_uri,
      code_verifier: verifier,
      code,
    }),
  });
  if (!res.ok) {
    console.error("Token exchange failed:", res.status, await res.text().catch(() => ""));
    window.history.replaceState({}, "", "/");
    return "failed";
  }

  const { access_token, refresh_token } = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
  };
  if (!access_token || !refresh_token) {
    console.error("Token exchange succeeded but returned no access_token/refresh_token");
    return "failed";
  }

  storeAccessToken(access_token);

  // Hand the refresh token to the backend to seal into an httpOnly cookie. The bearer
  // proves who we are so a session can't be planted. This is the only moment the
  // refresh token is ever visible to JS.
  const sealed = await fetch("/api/auth/session", {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${access_token}` },
    credentials: "include",
    body: JSON.stringify({ refresh_token }),
  }).catch(() => null);
  if (!sealed || !sealed.ok) {
    console.error("Could not persist the session cookie:", sealed?.status);
    clearLocalAuth();
    return "failed";
  }

  // Drop ?code= from the URL so a refresh doesn't retry a spent authorization code.
  window.history.replaceState({}, "", "/");
  return "ok";
}

// --- whoami --------------------------------------------------------------------

/** A 401 from whoami (after api/client.ts has already tried a refresh) means the
 *  session is genuinely gone. Anything else is a transient reach-the-server problem —
 *  the shell must not show the sign-in screen for it. */
export class WhoamiError extends Error {
  constructor(readonly kind: "anonymous" | "transient") {
    super(`whoami:${kind}`);
    this.name = "WhoamiError";
  }
}

export function useWhoami(enabled = true) {
  return useQuery({
    queryKey: ["whoami"],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/api/whoami");
      const status = response.status;
      if (error || !data) {
        throw new WhoamiError(status === 401 ? "anonymous" : "transient");
      }
      return data;
    },
    enabled,
    retry: (failureCount, err) =>
      err instanceof WhoamiError && err.kind === "transient" && failureCount < 2,
  });
}
