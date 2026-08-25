import { useEffect, useState } from "react";

import { InfoIcon } from "./icons";

const MCP_URL = "https://swolemates-production.up.railway.app/mcp";

const STEPS = [
  <>
    Open <strong>Claude Desktop → Settings → Connectors</strong>
  </>,
  <>
    Click <strong>Add custom connector</strong>
  </>,
  <>
    Name it <strong>Swolemates</strong>, paste the URL below
  </>,
  <>
    Click <strong>Add</strong>, then sign in with the same account you use here
  </>,
  <>Approve the connection</>,
];

/** Info icon next to a page heading; click reveals how to connect Claude Desktop
 *  to the Swolemates MCP server. Dismisses on an outside click. */
export function McpConnectInfo() {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest(".mcp-info")) setOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [open]);

  async function handleCopy() {
    await navigator.clipboard.writeText(MCP_URL);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <span className="mcp-info">
      <button
        type="button"
        className="mcp-info-trigger"
        aria-expanded={open}
        aria-label="How to connect Claude Desktop"
        onClick={() => setOpen((o) => !o)}
      >
        <InfoIcon className="mcp-info-icon" />
      </button>
      {open && (
        <div className="mcp-info-popover" role="dialog">
          <div className="mcp-info-arrow" />
          <p className="mcp-info-title">Use Swolemates from Claude</p>
          <ol className="mcp-info-steps">
            {STEPS.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
          <div className="mcp-info-url-row">
            <code>{MCP_URL}</code>
            <button type="button" onClick={handleCopy}>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="muted mcp-info-unlocks">
            Once connected, you can log workouts, check your nutrition, or pull your progress
            from any chat with Claude.
          </p>
        </div>
      )}
    </span>
  );
}
