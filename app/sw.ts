import { defaultCache } from "@serwist/turbopack/worker";
import type { PrecacheEntry, RuntimeCaching, SerwistGlobalConfig } from "serwist";
import { NetworkOnly, Serwist } from "serwist";

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

// This is a mutation-heavy, data-current app — food logs, workouts, and
// Supabase auth must never be served from a stale cache. Anything under
// /api/ (our own routes) or *.supabase.co (the backend) is explicitly
// network-only, ahead of the default caching rules below.
const networkOnlyRules: RuntimeCaching[] = [
  {
    matcher: /^\/api\/.*/i,
    handler: new NetworkOnly(),
  },
  {
    matcher: /^https:\/\/.*\.supabase\.co\/.*/i,
    handler: new NetworkOnly(),
  },
];

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [...networkOnlyRules, ...defaultCache],
});

serwist.addEventListeners();
