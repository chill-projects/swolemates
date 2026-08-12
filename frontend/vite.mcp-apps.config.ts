import { resolve } from "node:path";

import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

/**
 * Builds ONE MCP app (selected by APP_NAME, default "tmpx") into a self-contained
 * HTML file (JS/CSS inlined). Self-containment isn't an optimization — app iframes get
 * no external network unless the resource declares CSP domains, so a bundle with
 * external refs simply doesn't render in Claude.
 *
 * `npm run build:apps` invokes this once per subdirectory of src/mcp-apps, each with
 * its own APP_NAME, so adding a component is a new directory, not a new config file.
 * Output lands next to the SPA build; the backend serves it as the ui:// resource
 * and the SPA fetches it over HTTP for AppRenderer.
 */
const APP_NAME = process.env.APP_NAME ?? "tmpx";

export default defineConfig({
  root: resolve(__dirname, `src/mcp-apps/${APP_NAME}`),
  plugins: [viteSingleFile()],
  build: {
    // NOTE: `--outDir` on the CLI resolves against `root` (the component dir), which
    // is how the bundle once silently missed the Docker image. Use APPS_OUT_DIR
    // (resolved against frontend/) instead of CLI flags.
    outDir: resolve(__dirname, process.env.APPS_OUT_DIR ?? "../backend/static/mcp-apps"),
    emptyOutDir: false,
    rollupOptions: {
      input: resolve(__dirname, `src/mcp-apps/${APP_NAME}/${APP_NAME}.html`),
    },
  },
});
