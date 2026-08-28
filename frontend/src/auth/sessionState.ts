/**
 * What the shell knows about the session right now, and whether it should wait.
 *
 * Two rules, both learned the hard way, which is why they live in one named place
 * instead of as ternaries inside the render:
 *
 * 1. "Still checking" is not "signed out". Collapsing them is what made a transient
 *    whoami blip drop the user on the sign-in screen mid-session.
 * 2. An unexpired access token is enough to start painting. It's our own JWT, the next
 *    API call revalidates it server-side, and whoami corrects us within a round trip
 *    if it's been revoked. Blocking on whoami to confirm what the token already says
 *    is what made a hard refresh sit behind a full-screen "Signing in…".
 *
 * A genuine 401 outranks the token, because a revoked credential still decodes as
 * perfectly fresh.
 */

export type AuthState = "unknown" | "authenticated" | "anonymous";

export interface SessionSignals {
  /** whoami came back with a user. */
  hasWhoami: boolean;
  /** whoami returned a real 401 — not a network or 5xx failure. */
  whoamiSaysAnonymous: boolean;
  /** An access token with life left in it is in sessionStorage. */
  tokenLooksLive: boolean;
}

export function resolveAuthState(signals: SessionSignals): AuthState {
  if (signals.whoamiSaysAnonymous) return "anonymous";
  if (signals.hasWhoami || signals.tokenLooksLive) return "authenticated";
  return "unknown";
}

/**
 * Whether to hold the shell behind a loading message. Only while the answer is
 * genuinely unknown — plus the login callback, where the code exchange is in flight
 * and the URL still carries `?code=`.
 */
export function isShellBusy(options: {
  authState: AuthState;
  returningFromLogin: boolean;
  checksPending: boolean;
}): boolean {
  if (options.returningFromLogin) return true;
  return options.authState === "unknown" && options.checksPending;
}
