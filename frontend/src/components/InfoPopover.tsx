import { type ReactNode, useEffect, useState } from "react";

import { InfoIcon } from "./icons";

/** Info icon that reveals a small popover on click; dismisses on an outside click.
 *  Shared shell for page-heading info affordances — see McpConnectInfo and
 *  PartnerInviteInfo for the content that goes inside. */
export function InfoPopover({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest(".info-popover")) setOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [open]);

  return (
    <span className="info-popover">
      <button
        type="button"
        className="info-popover-trigger"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((o) => !o)}
      >
        <InfoIcon className="info-popover-icon" />
      </button>
      {open && (
        <div className="info-popover-content" role="dialog">
          <div className="info-popover-arrow" />
          {children}
        </div>
      )}
    </span>
  );
}
