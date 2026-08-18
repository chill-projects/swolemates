import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // No devOptions.enabled: the service worker only exists in the built app, never
      // in `vite dev` — keeps the dev proxy setup (backend/app/main.py isn't running
      // a build) simple and avoids a dev-only caching layer to reason about.
      // Manifest icons precache automatically; these two are only referenced via
      // <link> tags in index.html, so they need to be named explicitly.
      includeAssets: ["favicon.ico", "apple-touch-icon.png"],
      manifest: {
        name: "Swolemates",
        short_name: "Swolemates",
        description: "Workout logging, food tracking, and partner accountability.",
        start_url: "/",
        display: "standalone",
        background_color: "#111827",
        theme_color: "#111827",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icon-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // This is a mutation-heavy, data-current app — a stale cached response for any
        // of these would actively mislead the user, so a network failure here must
        // surface as a real error rather than silently falling back to the cached SPA
        // shell. mcp-apps bundles have no content hash and change under a stable URL
        // as slices land (see the backend's Cache-Control: no-store on them); excluding
        // them here is defense in depth on top of the build ordering (this build runs
        // with emptyOutDir before `build:apps` populates that subdirectory, so nothing
        // under mcp-apps/ exists yet at precache time regardless).
        navigateFallbackDenylist: [/^\/api/, /^\/mcp/, /^\/health/],
        globIgnores: ["mcp-apps/**"],
      },
    }),
  ],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
  build: {
    // The Dockerfile copies this straight into the Python image; there is no separate
    // frontend host. Keep it in sync with STATIC_DIR in backend/app/main.py.
    outDir: "../backend/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // In dev the SPA is on :5173 and the backend on :8000. Proxying keeps them
    // same-origin so the app never needs a separate code path for CORS or cookies.
    proxy: {
      "/api": "http://localhost:8000",
      "/mcp": "http://localhost:8000",
      "/mcp-apps": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
