import { useEffect, useRef, useState } from "react";

import { useGenerateInvite } from "../api/partner";
import { formatInstant, useUserTimezone } from "../lib/datetime";
import { InfoPopover } from "./InfoPopover";

/** Info icon next to the Partner heading, shown only while unlinked. Click reveals
 *  the invite link (generated on mount — generateInvite is idempotent server-side)
 *  and what a partner can/can't see. Was previously an always-visible card on the
 *  page itself; PartnerPage now just shows a one-line "no partner" status instead. */
export function PartnerInviteInfo() {
  const generate = useGenerateInvite();
  const triggered = useRef(false);
  const [copied, setCopied] = useState(false);
  const tz = useUserTimezone();

  useEffect(() => {
    if (triggered.current) return;
    triggered.current = true;
    generate.mutate();
  }, [generate]);

  const url = generate.data ? `${window.location.origin}/invite/${generate.data.code}` : null;

  async function handleCopy() {
    if (!url) return;
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <InfoPopover label="How partner invites work">
      <p className="info-popover-title">Invite a partner</p>
      <p className="muted">
        Share this link — whoever signs up through it becomes your accountability partner.
        They’ll see your workout streak, frequency, PRs, and nutrition streak — never your
        food logs or weight.
      </p>
      {generate.isError && <p className="error">{generate.error.message}</p>}
      {url && generate.data ? (
        <>
          <div className="info-popover-url-row">
            <code>{url}</code>
            <button type="button" onClick={handleCopy}>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="muted info-popover-footer">
            Expires {formatInstant(generate.data.expires_at, tz)}
          </p>
        </>
      ) : (
        !generate.isError && <p className="muted">Setting up your invite link…</p>
      )}
    </InfoPopover>
  );
}
