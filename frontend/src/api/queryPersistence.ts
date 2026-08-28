/**
 * Rehydrates the *identity* layer of the query cache on page load.
 *
 * A hard refresh in a live tab used to repaint the whole app from nothing: the shell
 * waited on `/api/auth/config` + `/api/whoami`, then the content area waited on
 * `/api/profile` — and because the nav is gated on the profile too, the chrome
 * disappeared and popped back in. Three full-width loaders, for data the tab had in
 * memory a moment earlier.
 *
 * Only three keys are persisted, and the omissions are the point. `profile`, `whoami`
 * and `authConfig` are identity and configuration: who you are, your timezone, whether
 * you've onboarded. Nutrition, workouts, streaks and templates are deliberately absent
 * — the PRD is explicit that stale food and workout data actively misleads, so those
 * keep `staleTime: 0` and their own inline section loaders, which is where a spinner
 * is honest.
 *
 * Even the persisted three are only a paint-ahead, never a source of truth: they land
 * with `staleTime: 0` like everything else, so each one refetches on mount and a
 * change made in another tab (or by Claude over MCP) corrects within one round trip.
 *
 * Storage is `sessionStorage` — the same place and lifetime as the access token. It
 * survives a reload of this tab and nothing else. A new tab has no token either, so it
 * cold-boots: that one really is a sign-in.
 */

import type { QueryClient } from "@tanstack/react-query";

const STORAGE_KEY = "swolemates.identity_cache";
const PERSISTED_KEYS = ["profile", "whoami", "authConfig"];

interface PersistedEntry {
  key: unknown[];
  data: unknown;
}

function isPersisted(queryKey: readonly unknown[]): boolean {
  return typeof queryKey[0] === "string" && PERSISTED_KEYS.includes(queryKey[0]);
}

/** Seed the cache from the last page load. Safe to call with nothing stored. */
export function hydrateQueryCache(queryClient: QueryClient): void {
  let raw: string | null = null;
  try {
    raw = sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return; // private mode / storage disabled — just cold-boot
  }
  if (!raw) return;

  try {
    const entries = JSON.parse(raw) as PersistedEntry[];
    for (const entry of entries) {
      if (Array.isArray(entry.key) && isPersisted(entry.key)) {
        queryClient.setQueryData(entry.key, entry.data);
      }
    }
  } catch {
    // Unparseable, or written by an older shape of this code. Start clean.
    clearPersistedCache();
  }
}

/** Mirror the persisted keys into storage as they change. Returns an unsubscribe. */
export function persistQueryCache(queryClient: QueryClient): () => void {
  let queued = false;

  function write(): void {
    queued = false;
    const entries: PersistedEntry[] = queryClient
      .getQueryCache()
      .getAll()
      .filter((query) => query.state.status === "success" && isPersisted(query.queryKey))
      .map((query) => ({ key: [...query.queryKey], data: query.state.data }));

    try {
      if (entries.length) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
      else sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // Quota or private mode. This is an optimization; losing it costs a repaint.
    }
  }

  return queryClient.getQueryCache().subscribe(() => {
    // Cache events arrive in bursts (fetch → success → render). One write per tick.
    if (queued) return;
    queued = true;
    queueMicrotask(write);
  });
}

/** Drop the paint-ahead copy. Called when the session ends, so the next load can't
 *  flash the previous account's name and targets before whoami corrects it. */
export function clearPersistedCache(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to do — there was no usable storage to write to either.
  }
}
