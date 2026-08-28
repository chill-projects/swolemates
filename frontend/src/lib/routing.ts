/**
 * The smallest client-side routing that removes full page reloads.
 *
 * Every nav tab used to be a plain `<a href>`, so switching pages tore the whole app
 * down and rebuilt it: bundle re-parse, an empty React Query cache, and a fresh
 * `/api/auth/config` + `/api/whoami` round trip before anything could paint. The shell
 * shows "Signing in…" for exactly that window, so a routine tab switch flashed it —
 * nothing was wrong with the session, the app was just cold-booting each time.
 *
 * This keeps the app's existing shape — components ask "what's the pathname?" and
 * switch on it — but makes the answer reactive and swaps browser navigation for
 * `history.pushState`. No route table, no nested routes, no dependency. If this app
 * ever needs URL params or per-route layouts, that's the moment for a real router.
 */

import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Back/forward don't go through navigate(), so the store listens for them too.
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

function getPathname(): string {
  return window.location.pathname;
}

/** The current pathname, re-rendering the caller whenever it changes. */
export function usePathname(): string {
  return useSyncExternalStore(subscribe, getPathname, getPathname);
}

/**
 * Navigate without reloading. `replace` rewrites the current entry instead of pushing
 * a new one — what the OAuth callback wants when it strips `?code=` off the URL, so
 * Back doesn't land on a spent authorization code.
 */
export function navigate(to: string, options: { replace?: boolean } = {}): void {
  const url = new URL(to, window.location.href);
  if (url.origin !== window.location.origin) {
    window.location.assign(to); // off-site: a real navigation is the only option
    return;
  }

  const next = url.pathname + url.search + url.hash;
  const current = window.location.pathname + window.location.search + window.location.hash;

  if (options.replace) {
    window.history.replaceState({}, "", next);
  } else {
    // Re-clicking the tab you're already on shouldn't stack history entries.
    if (next === current) return;
    window.history.pushState({}, "", next);
    // Browsers do this for a real navigation; a pushState has to be told.
    window.scrollTo(0, 0);
  }
  emit();
}

/**
 * One document-level handler rather than a custom `<Link>`: every internal anchor in
 * the app becomes a client-side navigation, and the markup stays plain `<a href>` —
 * real URLs that still cmd-click into a new tab, middle-click, and copy correctly.
 *
 * Returns a teardown so a test can uninstall it.
 */
export function interceptLinkClicks(): () => void {
  function onClick(event: MouseEvent): void {
    // Anything that isn't a plain left click stays the browser's: cmd/ctrl-click opens
    // a tab, shift-click a window, middle-click a background tab. Intercepting those
    // would quietly break behaviour people rely on.
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    const anchor = (event.target as Element | null)?.closest?.("a");
    const href = anchor?.getAttribute("href");
    if (!anchor || href === null || href === undefined) return;
    if (anchor.hasAttribute("download")) return;

    const target = anchor.getAttribute("target");
    if (target && target !== "_self") return;

    const url = new URL(href, window.location.href);
    if (url.origin !== window.location.origin) return; // off-site
    // In-page anchors (#section) are the browser's job, not ours.
    if (url.pathname === window.location.pathname && url.hash) return;

    event.preventDefault();
    navigate(url.pathname + url.search + url.hash);
  }

  document.addEventListener("click", onClick);
  return () => document.removeEventListener("click", onClick);
}
