/**
 * The chrome a component draws around itself depends on who's hosting it.
 *
 * In a chat host the bundle is the only thing on screen, so it needs its own padding
 * and ground. In the SPA it sits in a grid beside real `.card` elements, and that
 * padding insets its card relative to its siblings — the misalignment this fixes.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { SPA_HOST, applyHostChrome, isSpaHost } from "./hostChrome";

describe("isSpaHost", () => {
  it("recognises the SPA by the name AppRenderer announces", () => {
    expect(isSpaHost({ name: SPA_HOST, version: "1.0.0" })).toBe(true);
  });

  it("treats every other host as a chat host", () => {
    expect(isSpaHost({ name: "claude-ai", version: "1.0.0" })).toBe(false);
  });

  // getHostVersion() returns undefined before the handshake completes, and in hosts
  // that don't implement it. Standalone chrome is the safe answer: a component with
  // too much padding reads fine, one with none is flush against the window edge.
  it("assumes a chat host when the host is unknown", () => {
    expect(isSpaHost(undefined)).toBe(false);
    expect(isSpaHost(null)).toBe(false);
  });
});

describe("applyHostChrome", () => {
  beforeEach(() => {
    document.body.className = "";
  });

  it("marks the body so the stylesheet can drop its own padding in the SPA", () => {
    applyHostChrome({ name: SPA_HOST, version: "1.0.0" }, document);
    expect(document.body.classList.contains("in-spa")).toBe(true);
  });

  it("leaves the body alone in a chat host", () => {
    applyHostChrome({ name: "claude-ai", version: "1.0.0" }, document);
    expect(document.body.classList.contains("in-spa")).toBe(false);
  });

  it("is idempotent", () => {
    applyHostChrome({ name: SPA_HOST, version: "1.0.0" }, document);
    applyHostChrome({ name: SPA_HOST, version: "1.0.0" }, document);
    expect(document.body.className.split(/\s+/).filter((c) => c === "in-spa")).toHaveLength(1);
  });

  it("returns whether it decided this was the SPA, so callers can branch too", () => {
    expect(applyHostChrome({ name: SPA_HOST, version: "1.0.0" }, document)).toBe(true);
    expect(applyHostChrome(undefined, document)).toBe(false);
  });
});

/**
 * A source scan, in the spirit of dispatch-parity: a bundle that renders inside the
 * SPA's card grid has to opt into this, and a new one would otherwise regress the
 * alignment silently. `template` is excluded because it renders *inside* a Card rather
 * than as one, so it already ships with no chrome of its own.
 */
describe("every SPA-hosted bundle opts in", () => {
  const SOURCES = import.meta.glob("./*/main.ts", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  const STYLES = import.meta.glob("./*/*.html", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  /** Bundles that draw their own card and sit in the SPA's grid. */
  const CARD_BUNDLES = ["planned", "nutrition-day", "workout-live"];

  it.each(CARD_BUNDLES)("%s calls applyHostChrome", (bundle) => {
    const source = SOURCES[`./${bundle}/main.ts`];
    expect(source, `${bundle}/main.ts missing`).toBeDefined();
    expect(source).toContain("applyHostChrome");
  });

  it.each(CARD_BUNDLES)("%s drops its padding under .in-spa", (bundle) => {
    const html = STYLES[`./${bundle}/${bundle}.html`];
    expect(html, `${bundle}.html missing`).toBeDefined();
    expect(html).toMatch(/body\.in-spa\s*{[^}]*padding:\s*0/);
  });
});
