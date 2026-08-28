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
