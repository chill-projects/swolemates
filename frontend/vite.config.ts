import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
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
