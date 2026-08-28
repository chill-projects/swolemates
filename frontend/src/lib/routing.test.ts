import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { interceptLinkClicks, navigate } from "./routing";

let teardown: (() => void) | null = null;

beforeEach(() => {
  // jsdom has no layout, so scrollTo is unimplemented and logs on every push.
  vi.stubGlobal("scrollTo", vi.fn());
  window.history.replaceState({}, "", "/");
  document.body.innerHTML = "";
  teardown = interceptLinkClicks();
});

afterEach(() => {
  teardown?.();
  teardown = null;
  vi.unstubAllGlobals();
});

/** Builds an anchor, clicks it the way the given modifiers describe, and reports
 *  whether the click was intercepted (prevented) or left to the browser. */
function clickAnchor(
  attrs: Record<string, string>,
  init: MouseEventInit = {},
): { prevented: boolean } {
  const anchor = document.createElement("a");
  for (const [name, value] of Object.entries(attrs)) anchor.setAttribute(name, value);
  anchor.textContent = "go";
  document.body.append(anchor);

  const event = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0, ...init });
  anchor.dispatchEvent(event);
  return { prevented: event.defaultPrevented };
}

describe("navigate", () => {
  it("changes the pathname without reloading", () => {
    navigate("/nutrition");
    expect(window.location.pathname).toBe("/nutrition");
  });

  it("ignores a navigation to the page you're already on", () => {
    navigate("/partner");
    const before = window.history.length;
    navigate("/partner");
    expect(window.history.length).toBe(before);
  });

  it("replaces rather than pushes when asked", () => {
    // The OAuth callback strips `?code=` this way, so Back can't land on a spent code.
    navigate("/callback?code=abc", { replace: true });
    const before = window.history.length;
    navigate("/", { replace: true });
    expect(window.location.pathname).toBe("/");
    expect(window.history.length).toBe(before);
  });
});

describe("link interception", () => {
  it("takes over an ordinary internal link", () => {
    const { prevented } = clickAnchor({ href: "/templates" });
    expect(prevented).toBe(true);
    expect(window.location.pathname).toBe("/templates");
  });

  it.each([
    ["metaKey", { metaKey: true }],
    ["ctrlKey", { ctrlKey: true }],
    ["shiftKey", { shiftKey: true }],
    ["altKey", { altKey: true }],
  ])("leaves %s clicks to the browser", (_label, init) => {
    // cmd-click opens a new tab, shift-click a new window. Swallowing those would
    // break behaviour people use constantly.
    const { prevented } = clickAnchor({ href: "/nutrition" }, init);
    expect(prevented).toBe(false);
    expect(window.location.pathname).toBe("/");
  });

  it("leaves middle-clicks to the browser", () => {
    const { prevented } = clickAnchor({ href: "/nutrition" }, { button: 1 });
    expect(prevented).toBe(false);
  });

  it("leaves off-site, targeted, and download links alone", () => {
    expect(clickAnchor({ href: "https://workos.com/docs" }).prevented).toBe(false);
    expect(clickAnchor({ href: "/partner", target: "_blank" }).prevented).toBe(false);
    expect(clickAnchor({ href: "/export.csv", download: "" }).prevented).toBe(false);
    expect(window.location.pathname).toBe("/");
  });

  it("leaves in-page #anchors to the browser", () => {
    const { prevented } = clickAnchor({ href: "#section" });
    expect(prevented).toBe(false);
  });

  it("follows a click on a child element inside the link", () => {
    // The nav renders a dot span and a label span inside each anchor, so the event
    // target is usually not the <a> itself.
    const anchor = document.createElement("a");
    anchor.setAttribute("href", "/plan");
    const span = document.createElement("span");
    anchor.append(span);
    document.body.append(anchor);

    span.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
    expect(window.location.pathname).toBe("/plan");
  });

  it("stops intercepting once torn down", () => {
    teardown?.();
    teardown = null;
    const { prevented } = clickAnchor({ href: "/nutrition" });
    expect(prevented).toBe(false);
  });
});

describe("usePathname subscribers", () => {
  it("notifies on navigate and on back/forward", () => {
    const listener = vi.fn();
    window.addEventListener("popstate", listener);

    navigate("/nutrition");
    expect(window.location.pathname).toBe("/nutrition");

    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(listener).toHaveBeenCalled();
    window.removeEventListener("popstate", listener);
  });
});
