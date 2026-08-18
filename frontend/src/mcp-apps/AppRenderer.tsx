import { AppBridge, PostMessageTransport } from "@modelcontextprotocol/ext-apps/app-bridge";
import { useEffect, useRef, useState } from "react";

import { getToken } from "../auth/authkit";

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
  eventsUrl,
  height = 320,
}: {
  bundleUrl: string;
  /** Tool whose result seeds the app on load, mirroring how Claude pushes the
   *  originating tool's result into the iframe. */
  initialTool: string;
  onCallTool: ToolHandler;
  /** Optional SSE endpoint. Each `changed` event re-runs initialTool and pushes the
   *  fresh result into the app — live updates without the component ever polling. */
  eventsUrl?: string;
  height?: number;
}) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Starts at the fallback height and grows to fit content once the bundle reports
  // its real size — bundles opt into this via useAutoResize/autoResize (on by
  // default), which watches document.body with a ResizeObserver.
  const [contentHeight, setContentHeight] = useState(height);

  useEffect(() => {
    let cancelled = false;
    fetch(bundleUrl, { cache: "no-store" })
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
      setContentHeight(height);

      bridge = new AppBridge(
        null, // no MCP client — onCallTool supplies the backend
        { name: "swolemates-web", version: "1.0.0" },
        // Without serverTools the app's callServerTool silently never resolves —
        // the capability declaration is what authorizes tool proxying.
        { serverTools: {} },
      );
      bridge.addEventListener("sizechange", ({ height: newHeight }) => {
        if (newHeight) setContentHeight(newHeight);
      });
      bridge.oncalltool = async (params) => {
        const result = await onCallTool(
          params.name,
          (params.arguments ?? {}) as Record<string, unknown>,
        );
        return result;
      };
      const pushCurrent = async () => {
        if (!bridge || closed) return;
        const result = await onCallTool(initialTool, {});
        await bridge.sendToolResult(result);
      };

      bridge.addEventListener("initialized", () => {
        void (async () => {
          if (!bridge) return;
          // Mirror a real host: declare the originating tool call, then push its result.
          await bridge.sendToolInput({ arguments: {} });
          await pushCurrent();
        })();
      });

      const transport = new PostMessageTransport(contentWindow, contentWindow);
      await bridge.connect(transport);

      // Live updates: on every server-side change event, push a fresh result into the
      // app. Raw fetch instead of EventSource because the stream needs a bearer token.
      if (eventsUrl) {
        const listen = async () => {
          while (!closed) {
            try {
              const token = getToken();
              const res = await fetch(eventsUrl, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
                signal: abort.signal,
              });
              if (!res.ok || !res.body) throw new Error(`events: ${res.status}`);
              const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
              for (;;) {
                const { done, value } = await reader.read();
                if (done) break;
                if (value.includes("event: changed")) await pushCurrent();
              }
            } catch {
              if (closed) return;
            }
            // Stream ended or failed — back off briefly, then resubscribe.
            await new Promise((r) => setTimeout(r, 3000));
          }
        };
        void listen();
      }
    };

    const abort = new AbortController();
    iframe.addEventListener("load", start, { once: true });
    iframe.srcdoc = html;

    return () => {
      closed = true;
      abort.abort();
      void bridge?.close();
    };
  }, [html, initialTool, onCallTool, eventsUrl]);

  if (error) return <p className="error">{error}</p>;
  if (!html) return <p className="muted">Loading component…</p>;
  return (
    <iframe
      ref={iframeRef}
      title="Embedded app"
      sandbox="allow-scripts"
      style={{ width: "100%", height: contentHeight, border: "none" }}
    />
  );
}
