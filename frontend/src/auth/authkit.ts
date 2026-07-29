/**
 * AuthKit login for the browser: OAuth 2.1 authorization code + PKCE.
 *
 * Public client, so there is no secret and no client_secret exchange — PKCE is what
 * binds the code to this browser. The access token is held in sessionStorage rather
 * than localStorage so it dies with the tab and never outlives the session.
 */

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

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
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
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.client_id,
      redirect_uri: config.redirect_uri,
      resource: config.resource,
      code_verifier: verifier,
      code,
    }),
  });
  if (!res.ok) {
    console.error("Token exchange failed:", res.status, await res.text().catch(() => ""));
    window.history.replaceState({}, "", "/");
    return "failed";
  }

  const { access_token } = (await res.json()) as { access_token?: string };
  if (!access_token) {
    console.error("Token exchange succeeded but returned no access_token");
    return "failed";
  }

  sessionStorage.setItem(TOKEN_KEY, access_token);
  // Drop ?code= from the URL so a refresh doesn't retry a spent authorization code.
  window.history.replaceState({}, "", "/");
  return "ok";
}
