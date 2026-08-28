import { describe, expect, it } from "vitest";

import { isShellBusy, resolveAuthState, type SessionSignals } from "./sessionState";

const nothingKnown: SessionSignals = {
  hasWhoami: false,
  whoamiSaysAnonymous: false,
  tokenLooksLive: false,
};

describe("resolveAuthState", () => {
  it("is 'unknown' before anything has answered", () => {
    expect(resolveAuthState(nothingKnown)).toBe("unknown");
  });

  it("trusts a live token before whoami has answered", () => {
    // This is the hard-refresh case: sessionStorage survived, so the app can paint
    // immediately instead of waiting out a whoami round trip behind "Signing in…".
    expect(resolveAuthState({ ...nothingKnown, tokenLooksLive: true })).toBe("authenticated");
  });

  it("is authenticated once whoami answers, token or not", () => {
    expect(resolveAuthState({ ...nothingKnown, hasWhoami: true })).toBe("authenticated");
  });

  it("lets a real 401 outrank a token that still looks fresh", () => {
    // A revoked credential decodes as perfectly valid — only the server knows.
    expect(
      resolveAuthState({ hasWhoami: false, whoamiSaysAnonymous: true, tokenLooksLive: true }),
    ).toBe("anonymous");
  });

  it("stays 'unknown', not 'anonymous', when whoami fails transiently", () => {
    // The bug this rule exists for: a network blip must not look like a sign-out.
    expect(resolveAuthState(nothingKnown)).not.toBe("anonymous");
  });
});

describe("isShellBusy", () => {
  it("waits while the answer is genuinely unknown", () => {
    expect(
      isShellBusy({ authState: "unknown", returningFromLogin: false, checksPending: true }),
    ).toBe(true);
  });

  it("does not wait once a live token has answered the question", () => {
    // The regression: `busy` used to include whoami.isPending unconditionally, so a
    // hard refresh flashed "Signing in…" even with a perfectly good token in hand.
    expect(
      isShellBusy({ authState: "authenticated", returningFromLogin: false, checksPending: true }),
    ).toBe(false);
  });

  it("does not wait to tell an anonymous visitor to sign in", () => {
    expect(
      isShellBusy({ authState: "anonymous", returningFromLogin: false, checksPending: true }),
    ).toBe(false);
  });

  it("always waits through the login callback", () => {
    // The code exchange is in flight and the URL still carries ?code=.
    expect(
      isShellBusy({ authState: "authenticated", returningFromLogin: true, checksPending: false }),
    ).toBe(true);
  });

  it("stops waiting once the checks settle", () => {
    expect(
      isShellBusy({ authState: "unknown", returningFromLogin: false, checksPending: false }),
    ).toBe(false);
  });
});
