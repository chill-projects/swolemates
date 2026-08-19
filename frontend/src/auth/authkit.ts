/**
 * AuthKit login for the browser: OAuth 2.1 authorization code + PKCE.
 *
 * Public client, so the login leg has no secret — PKCE is what binds the code to this
 * browser. The access token lives in sessionStorage and dies with the tab. But WorkOS
 * access tokens are short-lived (5 min), so staying signed in also needs a refresh
 * token: requested via `scope=offline_access` at login, persisted in localStorage so it
 * survives tab close, and exchanged for a new access token through POST
 * /api/auth/refresh — the backend holds the client_secret that exchange requires, which
 * a browser never can. Refresh tokens rotate (single-use); each call's response
 * replaces the stored one.
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
const REFRESH_KEY = "swolemates.refresh_token";
const VERIFIER_KEY = "swolemates.pkce_verifier";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

/** Drops the access token only — a live refresh token can still mint a new one. */
export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

/** Full sign-out: neither stored token can be used to recover the session. */
export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  if (refreshTimer !== null) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

function storeSession(accessToken: string, refreshToken: string): void {
  sessionStorage.setItem(TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_KEY, refreshToken);
  scheduleRefresh(accessToken);
}

/** Reads `exp` out of a JWT without verifying it — we already trust our own token. */
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

let refreshTimer: ReturnType<typeof setTimeout> | null = null;

/** Arms a background refresh a minute before the access token expires, so an open tab
 *  never has to wait out a failed request before it recovers. */
function scheduleRefresh(accessToken: string): void {
  if (refreshTimer !== null) clearTimeout(refreshTimer);
  const expiresAt = tokenExpiryMs(accessToken);
  if (expiresAt === null) return;
  const delay = Math.max(expiresAt - Date.now() - 60_000, 0);
  refreshTimer = setTimeout(() => {
    void refreshSession();
  }, delay);
}

/** Exchanges the stored refresh token for a new access token via the backend. Returns
 *  false (and clears the session) if there was no refresh token or WorkOS rejected it. */
export async function refreshSession(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  let res: Response;
  try {
    res = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    // Network failure, not a rejected token — leave the session in place to retry later
    // rather than signing the user out over a dropped connection.
    return false;
  }

  if (!res.ok) {
    clearSession();
    return false;
  }

  const body = (await res.json()) as { access_token?: string; refresh_token?: string };
  if (!body.access_token || !body.refresh_token) {
    clearSession();
    return false;
  }
  storeSession(body.access_token, body.refresh_token);
  return true;
}

/** Called once on app startup: resumes a session from a stored refresh token if there's
 *  no live access token in this tab, and (re-)arms the proactive refresh timer either
 *  way, since a page reload always loses in-memory timer state. */
export async function bootstrapSession(): Promise<void> {
  const accessToken = getToken();
  if (accessToken) {
    scheduleRefresh(accessToken);
    return;
  }
  await refreshSession();
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const res = await fetch("/api/auth/config");
  if (!res.ok) throw new Error("Could not read auth configuration");
  return (await res.json()) as AuthConfig;
}

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
 * Complete the flow on /callback: swap the code for a token.
 *
 * "restart" means the PKCE verifier is missing — which happens legitimately when the
 * login continued in a different tab (e.g. WorkOS's email-verification link opens a new
 * one). The fix is simply to start the login again: AuthKit already has a session, so
 * the retry round-trips instantly and this tab gets its own code + verifier pair.
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

  storeSession(access_token, refresh_token);
  // Drop ?code= from the URL so a refresh doesn't retry a spent authorization code.
  window.history.replaceState({}, "", "/");
  return "ok";
}

export function useWhoami(enabled = true) {
  return useQuery({
    queryKey: ["whoami"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/whoami");
      if (error) throw new Error("Not authenticated");
      return data;
    },
    enabled,
    retry: false,
  });
}
