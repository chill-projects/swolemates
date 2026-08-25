import { useState } from "react";

import { InfoPopover } from "./InfoPopover";

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
 *  to the Swolemates MCP server. */
export function McpConnectInfo() {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(MCP_URL);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <InfoPopover label="How to connect Claude Desktop">
      <p className="info-popover-title">Use Swolemates from Claude</p>
      <ol className="info-popover-steps">
        {STEPS.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>
      <div className="info-popover-url-row">
        <code>{MCP_URL}</code>
        <button type="button" onClick={handleCopy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <p className="muted info-popover-footer">
        Once connected, you can log workouts, check your nutrition, or pull your progress from
        any chat with Claude.
      </p>
    </InfoPopover>
  );
}
