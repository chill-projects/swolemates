import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** A syntactically-valid-enough JWT for `tokenExpiryMs`: it only reads the middle
 *  segment as base64 JSON and pulls out `exp` (seconds). */
function fakeToken(expiresInSeconds: number): string {
  const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + expiresInSeconds }))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `header.${payload}.sig`;
}

type Authkit = typeof import("./authkit");

async function loadAuthkit(): Promise<Authkit> {
  vi.resetModules();
  return import("./authkit");
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  sessionStorage.clear();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("isTokenFresh", () => {
  it("is false for a missing, expired, or nearly-expired token", async () => {
    const { isTokenFresh } = await loadAuthkit();
    expect(isTokenFresh(null)).toBe(false);
    expect(isTokenFresh(fakeToken(-60))).toBe(false);
    expect(isTokenFresh(fakeToken(10))).toBe(false); // inside the 30s buffer
    expect(isTokenFresh("not.a.jwt")).toBe(false);
  });

  it("is true only with comfortable life left", async () => {
    const { isTokenFresh } = await loadAuthkit();
    expect(isTokenFresh(fakeToken(300))).toBe(true);
  });
});

describe("refreshSession", () => {
  it("stores the new access token and returns 'ok' on 200", async () => {
    const { refreshSession, getToken } = await loadAuthkit();
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { access_token: fakeToken(300) }));

    expect(await refreshSession()).toBe("ok");
    expect(getToken()).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/refresh",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });

  it("returns 'rejected' and drops the local token on 401", async () => {
    const { refreshSession, getToken } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(-1));
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Session expired" }));

    expect(await refreshSession()).toBe("rejected");
    expect(getToken()).toBeNull();
  });

  it("clears local state on a 401 the server coded 'session_expired'", async () => {
    const { refreshSession, getToken } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(-1));
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { detail: "Session expired", code: "session_expired" }),
    );

    expect(await refreshSession()).toBe("rejected");
    expect(getToken()).toBeNull();
  });

  it("drops the persisted identity cache when the session is rejected", async () => {
    // Otherwise the cached profile outlives the token and the next load paints the
    // old account for a beat before whoami corrects it.
    const { refreshSession } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(-1));
    sessionStorage.setItem("swolemates.identity_cache", JSON.stringify([{ key: ["profile"] }]));
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { detail: "Session expired", code: "session_expired" }),
    );

    expect(await refreshSession()).toBe("rejected");
    expect(sessionStorage.getItem("swolemates.identity_cache")).toBeNull();
  });

  it("keeps local state on a 401 the server coded 'no_session'", async () => {
    // No cookie was sent, so nothing was rejected — reporting signed-out is right, but
    // tearing down a token that was never refused is not.
    const { refreshSession, getToken } = await loadAuthkit();
    const live = fakeToken(-1);
    sessionStorage.setItem("swolemates.access_token", live);
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { detail: "No session", code: "no_session" }),
    );

    expect(await refreshSession()).toBe("rejected");
    expect(getToken()).toBe(live);
  });

  it("returns 'error' (not 'rejected') on a 502 and keeps the token", async () => {
    const { refreshSession } = await loadAuthkit();
    const live = fakeToken(-1);
    sessionStorage.setItem("swolemates.access_token", live);
    fetchMock.mockResolvedValueOnce(jsonResponse(502, { detail: "Auth provider unavailable" }));

    expect(await refreshSession()).toBe("error");
    expect(sessionStorage.getItem("swolemates.access_token")).toBe(live);
  });

  it("returns 'error' on a network failure", async () => {
    const { refreshSession } = await loadAuthkit();
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    expect(await refreshSession()).toBe("error");
  });

  it("coalesces concurrent callers into a single request", async () => {
    const { refreshSession } = await loadAuthkit();
    fetchMock.mockResolvedValue(jsonResponse(200, { access_token: fakeToken(300) }));

    const [a, b, c] = await Promise.all([refreshSession(), refreshSession(), refreshSession()]);

    expect([a, b, c]).toEqual(["ok", "ok", "ok"]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("skips the network entirely when the token is already fresh", async () => {
    const { refreshSession } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(300));

    expect(await refreshSession()).toBe("ok");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("caches a rejection briefly so a burst of requests doesn't hammer /refresh", async () => {
    const { refreshSession } = await loadAuthkit();
    fetchMock.mockResolvedValueOnce(jsonResponse(401, {}));

    expect(await refreshSession()).toBe("rejected");
    expect(await refreshSession()).toBe("rejected");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("bootstrapSession", () => {
  it("returns 'ok' without a network call when a fresh token is already present", async () => {
    const { bootstrapSession } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(300));

    expect(await bootstrapSession()).toBe("ok");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refreshes when the stored token is stale", async () => {
    const { bootstrapSession } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(-30));
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { access_token: fakeToken(300) }));

    expect(await bootstrapSession()).toBe("ok");
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});

describe("clearSession", () => {
  it("tells the backend to drop the cookie", async () => {
    const { clearSession } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(300));
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    clearSession();

    expect(sessionStorage.getItem("swolemates.access_token")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/logout",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });
});

describe("the background refresh chain", () => {
  /** Drives fake timers far enough to run the chain, letting each tick's promises
   *  settle so the next `setTimeout` is armed before time advances again. */
  async function advance(ms: number, steps = 6): Promise<void> {
    for (let i = 0; i < steps; i++) {
      await vi.advanceTimersByTimeAsync(Math.ceil(ms / steps));
    }
  }

  it("wakes up after the token goes stale, not exactly on the boundary", async () => {
    // The regression: the wake-up was scheduled at exactly `expiry - buffer`, the
    // instant the token stops being fresh. Fire a hair early — which real timers do —
    // and refreshSession() still saw a fresh token, no-opped, and returned "ok"
    // without storing anything; since only storeAccessToken() re-armed, background
    // refresh silently died for the life of the tab. The slop is what guarantees the
    // token is genuinely stale by the time the callback runs.
    vi.useFakeTimers();
    const { bootstrapSession } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(60));
    fetchMock.mockResolvedValue(jsonResponse(200, { access_token: fakeToken(60) }));

    await bootstrapSession();

    // 60s life - 30s buffer: the old code fired right here, on the knife edge.
    await vi.advanceTimersByTimeAsync(30_000);
    expect(fetchMock).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(2_000);
    expect(fetchMock).toHaveBeenCalled();
  });

  it("keeps re-arming across many refresh cycles", async () => {
    vi.useFakeTimers();
    const { bootstrapSession } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(60));
    fetchMock.mockResolvedValue(jsonResponse(200, { access_token: fakeToken(60) }));

    await bootstrapSession();
    await advance(200_000, 40);

    // ~31s per cycle — several cycles' worth, so a chain that dies after one shows up.
    expect(fetchMock.mock.calls.length).toBeGreaterThan(3);
  });

  it("keeps retrying after more than one consecutive failure", async () => {
    // The backoff used to be one-shot: a second failure ended the chain for good.
    vi.useFakeTimers();
    const { bootstrapSession } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(60));
    fetchMock.mockResolvedValue(jsonResponse(502, { detail: "Auth provider unavailable" }));

    await bootstrapSession();
    await advance(45_000);
    const afterFirst = fetchMock.mock.calls.length;
    expect(afterFirst).toBeGreaterThan(0);

    await advance(300_000, 30);
    expect(fetchMock.mock.calls.length).toBeGreaterThan(afterFirst + 1);
  });

  it("stops the chain once the session is genuinely rejected", async () => {
    vi.useFakeTimers();
    const { bootstrapSession } = await loadAuthkit();
    sessionStorage.setItem("swolemates.access_token", fakeToken(60));
    fetchMock.mockResolvedValue(
      jsonResponse(401, { detail: "Session expired", code: "session_expired" }),
    );

    await bootstrapSession();
    await advance(60_000);
    const afterRejection = fetchMock.mock.calls.length;

    await advance(600_000, 30);
    expect(fetchMock.mock.calls.length).toBe(afterRejection);
  });
});
