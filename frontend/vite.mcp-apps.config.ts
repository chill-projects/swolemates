import { resolve } from "node:path";

import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

/**
 * Builds each MCP app into ONE self-contained HTML file (JS/CSS inlined).
 * Self-containment isn't an optimization — app iframes get no external network
 * unless the resource declares CSP domains, so a bundle with external refs
 * simply doesn't render in Claude.
 *
 * Output lands next to the SPA build; the backend serves it as the ui:// resource
 * and the SPA fetches it over HTTP for AppRenderer.
 */
export default defineConfig({
  root: resolve(__dirname, "src/mcp-apps/tmpx"),
  plugins: [viteSingleFile()],
  build: {
    // NOTE: `--outDir` on the CLI resolves against `root` (the component dir), which
    // is how the bundle once silently missed the Docker image. Use APPS_OUT_DIR
    // (resolved against frontend/) instead of CLI flags.
    outDir: resolve(__dirname, process.env.APPS_OUT_DIR ?? "../backend/static/mcp-apps"),
    emptyOutDir: false,
    rollupOptions: {
      input: resolve(__dirname, "src/mcp-apps/tmpx/tmpx.html"),
    },
  },
});
