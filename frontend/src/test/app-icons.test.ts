/**
 * The app's mark is named in three places that can drift apart from the files in
 * public/: index.html (the browser tab), the web manifest in vite.config.ts (the
 * installed app's home-screen and launcher icon), and — on the backend — MCP's
 * serverInfo.icons and the ui:// component resources (backend/tests/test_branding.py
 * covers that side).
 *
 * A rename on any one side fails silently. The fetcher gets a miss and falls back to
 * a mark derived from the hostname, which on *.up.railway.app is Railway's, so the
 * app quietly wears someone else's logo. Nothing throws, no test goes red, and the
 * build still succeeds — hence this.
 *
 * Read through Vite (`?raw`, `import.meta.glob`) rather than node:fs so the frontend
 * doesn't take on @types/node for one test. vite.config.ts is read as text because
 * vite-plugin-pwa builds the manifest into its own plugin instance and never hands
 * the options back — the config source is the only place that list can be read from.
 */

import { describe, expect, it } from "vitest";

import appTsx from "../App.tsx?raw";
import indexHtml from "../../index.html?raw";
import viteConfig from "../../vite.config.ts?raw";

/** public/ filenames, from the keys alone — the glob is lazy, so nothing is loaded. */
const SHIPPED = new Set(
  Object.keys(import.meta.glob("../../public/*")).map((p) => p.split("/").pop()!),
);

/** Every `href` on an icon <link> in index.html, as a public/-relative filename. */
function indexHtmlIconHrefs(): string[] {
  const links = indexHtml.match(/<link[^>]*rel="(?:icon|apple-touch-icon)"[^>]*>/g) ?? [];
  return links.map((tag) => {
    const href = tag.match(/href="([^"]+)"/)?.[1];
    expect(href, `icon <link> with no href: ${tag}`).toBeDefined();
    return href!.replace(/^\//, "");
  });
}

/** Every `src` in the web manifest's icons array in vite.config.ts. */
function manifestIconSrcs(): string[] {
  const icons = viteConfig.match(/src:\s*"\/([^"]+)"/g) ?? [];
  return icons.map((m) => m.replace(/^src:\s*"\//, "").replace(/"$/, ""));
}

describe("the app icon", () => {
  it("is declared for the browser tab, at more than one size", () => {
    const hrefs = indexHtmlIconHrefs();

    // The .ico alone leaves consumers that read `sizes` to pick a bitmap — link-preview
    // crawlers, and hosts that draw a site's mark beside a link — with only 48px to
    // work from, and several skip it and derive a mark from the hostname instead.
    expect(hrefs).toContain("favicon.ico");
    expect(hrefs).toContain("icon-192.png");
  });

  it("is declared for the installed app on both platforms", () => {
    // Android crops a launcher icon to the platform's mask and wants the maskable
    // variant; everything else takes the largest plain one. iOS never reads the
    // manifest at all — apple-touch-icon.png in index.html is its only route in.
    expect(manifestIconSrcs()).toContain("icon-512.png");
    expect(manifestIconSrcs()).toContain("icon-maskable-512.png");
    expect(indexHtmlIconHrefs()).toContain("apple-touch-icon.png");
  });

  it("names files that public/ actually ships", () => {
    for (const name of [...indexHtmlIconHrefs(), ...manifestIconSrcs()]) {
      expect(SHIPPED, `${name} is not in public/`).toContain(name);
    }
  });

  it("is what an unfurler draws for a pasted link", () => {
    // A link with no og:image falls back to the favicon at best and to a
    // hostname-derived mark at worst — the same failure, one surface over.
    expect(indexHtml).toContain('property="og:image" content="/icon-512.png"');
    expect(SHIPPED).toContain("icon-512.png");
  });

  it("is the same mark the app bar renders", () => {
    // App.tsx points at icon-192.png so the mark in the header and the mark in the
    // tab can't diverge. If that ever moves to its own asset, this is the reminder
    // that there are now two files to regenerate from design/logo-source.jpg.
    expect(appTsx).toContain('src="/icon-192.png"');
  });
});
