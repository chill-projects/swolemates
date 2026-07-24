"use client";

import { useEffect } from "react";

// Running `next build && next start` locally (e.g. to test PWA
// installability) registers a real service worker in the browser. That
// registration persists across origins/sessions even after switching back
// to `next dev` — and its caching rules can then serve stale JS chunks
// indefinitely, since a service worker intercepts fetches before they ever
// reach the network. This wipes any such leftover registration whenever the
// app runs in development, so a stray prod-mode test can't cause confusing,
// hard-to-diagnose staleness during regular dev work.
export function DevServiceWorkerCleanup() {
  useEffect(() => {
    if (process.env.NODE_ENV === "production") return;
    if (!("serviceWorker" in navigator)) return;

    navigator.serviceWorker.getRegistrations().then((registrations) => {
      for (const registration of registrations) {
        registration.unregister();
      }
    });

    if ("caches" in window) {
      caches.keys().then((keys) => {
        for (const key of keys) {
          caches.delete(key);
        }
      });
    }
  }, []);

  return null;
}
