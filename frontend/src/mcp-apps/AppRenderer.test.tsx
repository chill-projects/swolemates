import { render, waitFor } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { AppRenderer, type ToolResultPayload } from "./AppRenderer";

vi.mock("../auth/authkit", () => ({ getToken: () => "test-token" }));

const BUNDLE = "<!doctype html><html><body>bundle</body></html>";

/** Counts iframe re-seeds. Assigning `srcdoc` is what reloads the bundle — it
 *  throws away the component's state, resets the reported height, and so scrolls
 *  the host page. Anything that does it more than once per mount is the bug this
 *  file exists for. */
function watchSrcdocWrites(): { count: () => number; restore: () => void } {
  const proto = HTMLIFrameElement.prototype;
  const original = Object.getOwnPropertyDescriptor(proto, "srcdoc");
  let writes = 0;
  Object.defineProperty(proto, "srcdoc", {
    configurable: true,
    get() {
      return original?.get?.call(this) as string;
    },
    set(value: string) {
      writes += 1;
      original?.set?.call(this, value);
    },
  });
  return {
    count: () => writes,
    restore: () => {
      if (original) Object.defineProperty(proto, "srcdoc", original);
    },
  };
}

let srcdoc: ReturnType<typeof watchSrcdocWrites>;

beforeEach(() => {
  srcdoc = watchSrcdocWrites();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(BUNDLE, { status: 200 }))),
  );
});

afterEach(() => {
  srcdoc.restore();
  vi.unstubAllGlobals();
});

const noopTool = async (): Promise<ToolResultPayload> => ({ content: [{ type: "text", text: "{}" }] });

describe("AppRenderer", () => {
  it("seeds the iframe once", async () => {
    render(<AppRenderer bundleUrl="/mcp-apps/x.html" initialTool="get_x" onCallTool={noopTool} />);
    await waitFor(() => expect(srcdoc.count()).toBe(1));
  });

  /**
   * The regression this whole ref dance is for. PlanPage's template handler closes
   * over a TanStack Query result and refetches after every write, so its identity
   * changes on every save. While `onCallTool` was an effect dependency that tore the
   * iframe down and rebuilt it mid-edit — which is what "the page keeps refreshing
   * and I lose my scroll position" actually was.
   */
  it("does not re-seed when the tool handler's identity changes", async () => {
    const { rerender } = render(
      <AppRenderer bundleUrl="/mcp-apps/x.html" initialTool="get_x" onCallTool={noopTool} />,
    );
    await waitFor(() => expect(srcdoc.count()).toBe(1));

    for (let i = 0; i < 3; i += 1) {
      rerender(
        <AppRenderer
          bundleUrl="/mcp-apps/x.html"
          initialTool="get_x"
          onCallTool={async () => noopTool()}
        />,
      );
    }

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(srcdoc.count()).toBe(1);
  });

  it("re-seeds when the bundle itself changes", async () => {
    const { rerender } = render(
      <AppRenderer bundleUrl="/mcp-apps/x.html" initialTool="get_x" onCallTool={noopTool} />,
    );
    await waitFor(() => expect(srcdoc.count()).toBe(1));
    rerender(
      <AppRenderer bundleUrl="/mcp-apps/y.html" initialTool="get_y" onCallTool={noopTool} />,
    );
    await waitFor(() => expect(srcdoc.count()).toBe(2));
  });
});
