import { QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearPersistedCache, hydrateQueryCache, persistQueryCache } from "./queryPersistence";

const STORAGE_KEY = "swolemates.identity_cache";

let queryClient: QueryClient;
let stopPersisting: (() => void) | null = null;

beforeEach(() => {
  sessionStorage.clear();
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  stopPersisting?.();
  stopPersisting = null;
  vi.unstubAllGlobals();
});

/** The subscriber batches writes into a microtask, so let one drain. */
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function stored(): { key: unknown[]; data: unknown }[] {
  return JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]") as {
    key: unknown[];
    data: unknown;
  }[];
}

describe("persistQueryCache", () => {
  it("mirrors the identity queries into sessionStorage", async () => {
    stopPersisting = persistQueryCache(queryClient);
    queryClient.setQueryData(["profile"], { timezone: "America/New_York" });
    queryClient.setQueryData(["whoami"], { sub: "user_123" });
    await flush();

    const keys = stored().map((entry) => entry.key[0]);
    expect(keys).toContain("profile");
    expect(keys).toContain("whoami");
  });

  it("never persists food or workout data", async () => {
    // The PRD is explicit that stale nutrition/workout data actively misleads. These
    // keep staleTime: 0 and their own inline loaders instead.
    stopPersisting = persistQueryCache(queryClient);
    queryClient.setQueryData(["profile"], { timezone: "UTC" });
    queryClient.setQueryData(["nutritionDay", "2026-08-28"], { calories: 1800 });
    queryClient.setQueryData(["workoutHistory"], [{ id: 1 }]);
    queryClient.setQueryData(["nutritionCalendar"], { days: [] });
    await flush();

    expect(stored().map((entry) => entry.key[0])).toEqual(["profile"]);
  });

  it("survives storage that refuses to be written", async () => {
    vi.stubGlobal("sessionStorage", {
      getItem: () => null,
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
      removeItem: () => {},
    });

    stopPersisting = persistQueryCache(queryClient);
    queryClient.setQueryData(["profile"], { timezone: "UTC" });
    await expect(flush()).resolves.not.toThrow();
  });
});

describe("hydrateQueryCache", () => {
  it("paints the previous load's identity data straight into a fresh client", async () => {
    stopPersisting = persistQueryCache(queryClient);
    queryClient.setQueryData(["profile"], { timezone: "Europe/Berlin" });
    await flush();
    stopPersisting();
    stopPersisting = null;

    // A reload: brand new client, same sessionStorage.
    const reloaded = new QueryClient();
    hydrateQueryCache(reloaded);

    expect(reloaded.getQueryData(["profile"])).toEqual({ timezone: "Europe/Berlin" });
  });

  it("ignores keys outside the allowlist even if storage says otherwise", () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { key: ["profile"], data: { timezone: "UTC" } },
        { key: ["nutritionDay", "2026-08-28"], data: { calories: 99 } },
      ]),
    );

    hydrateQueryCache(queryClient);

    expect(queryClient.getQueryData(["profile"])).toEqual({ timezone: "UTC" });
    expect(queryClient.getQueryData(["nutritionDay", "2026-08-28"])).toBeUndefined();
  });

  it("starts clean on unparseable storage instead of throwing", () => {
    sessionStorage.setItem(STORAGE_KEY, "{not json");

    expect(() => hydrateQueryCache(queryClient)).not.toThrow();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("is a no-op when nothing was stored", () => {
    expect(() => hydrateQueryCache(queryClient)).not.toThrow();
    expect(queryClient.getQueryData(["profile"])).toBeUndefined();
  });

  it("leaves hydrated data stale, so it refetches rather than being trusted", () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([{ key: ["profile"], data: { timezone: "UTC" } }]),
    );
    hydrateQueryCache(queryClient);

    const query = queryClient.getQueryCache().find({ queryKey: ["profile"] });
    // staleTime is 0 app-wide; the paint-ahead copy gets no special protection.
    expect(query?.isStaleByTime(0)).toBe(true);
  });
});

describe("clearPersistedCache", () => {
  it("drops the stored copy", () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([{ key: ["profile"], data: {} }]));
    clearPersistedCache();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
