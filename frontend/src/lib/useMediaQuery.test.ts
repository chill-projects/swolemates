import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useMediaQuery } from "./useMediaQuery";

type Listener = (event: { matches: boolean }) => void;

/** A matchMedia stand-in — jsdom has none — that can flip and notify. */
function stubMatchMedia(initial: boolean) {
  const listeners = new Set<Listener>();
  let matches = initial;
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      get matches() {
        return matches;
      },
      media: query,
      addEventListener: (_: string, fn: Listener) => listeners.add(fn),
      removeEventListener: (_: string, fn: Listener) => listeners.delete(fn),
    })),
  );
  return {
    flip(next: boolean) {
      matches = next;
      for (const fn of listeners) fn({ matches: next });
    },
    get listenerCount() {
      return listeners.size;
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useMediaQuery", () => {
  it("reports the query's current state on first render", () => {
    stubMatchMedia(true);
    const { result } = renderHook(() => useMediaQuery("(max-width: 52rem)"));
    expect(result.current).toBe(true);
  });

  it("follows the query when it changes", () => {
    const media = stubMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(max-width: 52rem)"));
    expect(result.current).toBe(false);

    act(() => media.flip(true));
    expect(result.current).toBe(true);
  });

  it("unsubscribes on unmount", () => {
    const media = stubMatchMedia(false);
    const { unmount } = renderHook(() => useMediaQuery("(max-width: 52rem)"));
    expect(media.listenerCount).toBe(1);
    unmount();
    expect(media.listenerCount).toBe(0);
  });

  // Thumbnail capture and some embedded viewers have no matchMedia at all; the
  // desktop layout is the safe answer there, not a crash.
  it("falls back to false where matchMedia does not exist", () => {
    vi.stubGlobal("matchMedia", undefined);
    const { result } = renderHook(() => useMediaQuery("(max-width: 52rem)"));
    expect(result.current).toBe(false);
  });
});
