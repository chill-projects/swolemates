import { AppBridge, PostMessageTransport } from "@modelcontextprotocol/ext-apps/app-bridge";
import { useEffect, useRef, useState } from "react";

export type ToolResultPayload = {
  content: Array<{ type: "text"; text: string }>;
  structuredContent?: Record<string, unknown>;
};

export type ToolHandler = (
  name: string,
  args: Record<string, unknown>,
) => Promise<ToolResultPayload>;

/**
 * Hosts an MCP app bundle inside the SPA — the second front door for the same
 * component Claude renders. The iframe + postMessage protocol are identical to a real
 * MCP host; only the tool transport differs: `onCallTool` backs the app's tool calls
 * with our REST API instead of an MCP session.
 *
 * The iframe is sandboxed to scripts only, matching the deny-by-default posture real
 * hosts apply. The bundle is fetched same-origin and injected via srcdoc.
 */
export function AppRenderer({
  bundleUrl,
  initialTool,
  onCallTool,
  height = 320,
}: {
  bundleUrl: string;
  /** Tool whose result seeds the app on load, mirroring how Claude pushes the
   *  originating tool's result into the iframe. */
  initialTool: string;
  onCallTool: ToolHandler;
  height?: number;
}) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(bundleUrl)
      .then(async (res) => {
        if (!res.ok) throw new Error(`${res.status} fetching ${bundleUrl}`);
        const text = await res.text();
        if (!cancelled) setHtml(text);
      })
      .catch(() => {
        if (!cancelled) setError("Component bundle not found. Run `make apps` and rebuild.");
      });
    return () => {
      cancelled = true;
    };
  }, [bundleUrl]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!html || !iframe) return;

    let bridge: AppBridge | null = null;
    let closed = false;

    const start = async () => {
      const contentWindow = iframe.contentWindow;
      if (!contentWindow || closed) return;

      bridge = new AppBridge(
        null, // no MCP client — onCallTool supplies the backend
        { name: "swolemates-web", version: "1.0.0" },
        // Without serverTools the app's callServerTool silently never resolves —
        // the capability declaration is what authorizes tool proxying.
        { serverTools: {} },
      );
      bridge.oncalltool = async (params) => {
        const result = await onCallTool(
          params.name,
          (params.arguments ?? {}) as Record<string, unknown>,
        );
        return result;
      };
      bridge.addEventListener("initialized", () => {
        void (async () => {
          if (!bridge) return;
          // Mirror a real host: declare the originating tool call, then push its result.
          await bridge.sendToolInput({ arguments: {} });
          const result = await onCallTool(initialTool, {});
          await bridge.sendToolResult(result);
        })();
      });

      const transport = new PostMessageTransport(contentWindow, contentWindow);
      await bridge.connect(transport);
    };

    iframe.addEventListener("load", start, { once: true });
    iframe.srcdoc = html;

    return () => {
      closed = true;
      void bridge?.close();
    };
  }, [html, initialTool, onCallTool]);

  if (error) return <p className="error">{error}</p>;
  if (!html) return <p className="muted">Loading component…</p>;
  return (
    <iframe
      ref={iframeRef}
      title="TmpX component"
      sandbox="allow-scripts"
      style={{ width: "100%", height, border: "none" }}
    />
  );
}
