/**
 * PROTOTYPE — throwaway. Not wired into the real ProfileForm/App flow yet.
 *
 * Question: what should the "info icon that explains how to connect Claude Desktop"
 * affordance on Profile settings look like? Three structurally different reveal
 * patterns, switchable via `?variant=` on /profile. See the floating bar at the
 * bottom of the screen once mounted.
 *
 * To view: temporarily render <ProfileMcpInfoPrototypeSwitcher /> next to the
 * "Profile settings" <h2> in App.tsx, then visit /profile?variant=A (or B, or C).
 * Delete this file (and the App.tsx import) once a variant is picked and folded
 * into the real component — see docs/legacy-style throwaway-branch capture in the
 * prototype skill.
 */

import { useEffect, useState } from "react";

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

const UNLOCKS =
  "Once connected, you can log workouts, check your nutrition, or pull your progress from any chat with Claude.";

/* ---------------------------------------------------------------------------
 * Shared bits
 * ------------------------------------------------------------------------- */

function InfoIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

function XIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

function ChevronIcon({ className, open }: { className?: string; open: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 150ms" }}
      aria-hidden
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function CopyRow() {
  const [copied, setCopied] = useState(false);
  return (
    <div className="proto-copy-row">
      <code>{MCP_URL}</code>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard.writeText(MCP_URL).catch(() => {});
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function StepsList() {
  return (
    <ol className="proto-steps">
      {STEPS.map((step, i) => (
        // eslint-disable-next-line react/no-array-index-key -- static list, prototype only
        <li key={i}>{step}</li>
      ))}
    </ol>
  );
}

/* ---------------------------------------------------------------------------
 * Variant A — anchored popover. Click the icon, a small card floats below it.
 * Dismiss by clicking the icon again or anywhere outside. Lowest ceremony —
 * the rest of the page stays fully visible and interactive.
 * ------------------------------------------------------------------------- */
export function VariantA() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(".proto-popover-wrap")) setOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [open]);

  return (
    <span className="proto-popover-wrap">
      <button
        type="button"
        className="proto-icon-btn"
        aria-expanded={open}
        aria-label="How to connect Claude Desktop"
        onClick={() => setOpen((o) => !o)}
      >
        <InfoIcon className="proto-icon" />
      </button>
      {open && (
        <div className="proto-popover" role="dialog">
          <div className="proto-popover-arrow" />
          <p className="proto-popover-title">Use Swolemates from Claude</p>
          <StepsList />
          <CopyRow />
          <p className="muted proto-unlocks">{UNLOCKS}</p>
        </div>
      )}
    </span>
  );
}

/* ---------------------------------------------------------------------------
 * Variant B — modal dialog. Click the icon, a centered overlay takes over the
 * screen. Highest ceremony — forces the instructions to be read/dismissed
 * before returning to the form.
 * ------------------------------------------------------------------------- */
export function VariantB() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="proto-icon-btn"
        aria-label="How to connect Claude Desktop"
        onClick={() => setOpen(true)}
      >
        <InfoIcon className="proto-icon" />
      </button>
      {open && (
        <div className="proto-modal-backdrop" onClick={() => setOpen(false)}>
          <div className="proto-modal" role="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="proto-modal-header">
              <h3>Use Swolemates from Claude</h3>
              <button type="button" className="proto-icon-btn" onClick={() => setOpen(false)}>
                <XIcon className="proto-icon" />
              </button>
            </div>
            <StepsList />
            <CopyRow />
            <p className="muted proto-unlocks">{UNLOCKS}</p>
            <button type="button" className="proto-modal-done" onClick={() => setOpen(false)}>
              Got it
            </button>
          </div>
        </div>
      )}
    </>
  );
}

/* ---------------------------------------------------------------------------
 * Variant C — inline expanding row. Not a small icon-triggered popup at all:
 * a permanent "Connect to Claude" row sits above the form and expands in
 * place (pushing the form down), no overlay, no floating anything. Most
 * integrated into the page; best if this is something people reopen often
 * rather than see once.
 * ------------------------------------------------------------------------- */
export function VariantC() {
  const [open, setOpen] = useState(false);

  return (
    <div className="proto-inline-section">
      <button
        type="button"
        className="proto-inline-row"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <InfoIcon className="proto-icon" />
        <span>Connect to Claude</span>
        <ChevronIcon className="proto-icon proto-chevron" open={open} />
      </button>
      {open && (
        <div className="proto-inline-body">
          <p className="proto-popover-title">Use Swolemates from Claude</p>
          <StepsList />
          <CopyRow />
          <p className="muted proto-unlocks">{UNLOCKS}</p>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Switcher — mount this next to the "Profile settings" heading to compare.
 * ------------------------------------------------------------------------- */
const VARIANTS = {
  A: { Component: VariantA, name: "Anchored popover" },
  B: { Component: VariantB, name: "Modal dialog" },
  C: { Component: VariantC, name: "Inline expand" },
} as const;
type VariantKey = keyof typeof VARIANTS;

function currentVariant(): VariantKey {
  const v = new URLSearchParams(window.location.search).get("variant");
  return v && v in VARIANTS ? (v as VariantKey) : "A";
}

export function ProfileMcpInfoPrototypeSwitcher() {
  const [variant, setVariant] = useState<VariantKey>(currentVariant);

  function go(next: VariantKey) {
    const url = new URL(window.location.href);
    url.searchParams.set("variant", next);
    window.history.replaceState({}, "", url);
    setVariant(next);
  }

  function cycle(dir: 1 | -1) {
    const keys = Object.keys(VARIANTS) as VariantKey[];
    const i = keys.indexOf(variant);
    go(keys[(i + dir + keys.length) % keys.length]!);
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const active = document.activeElement;
      if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || (active as HTMLElement).isContentEditable)) {
        return;
      }
      if (e.key === "ArrowLeft") cycle(-1);
      if (e.key === "ArrowRight") cycle(1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- prototype only
  }, [variant]);

  const { Component, name } = VARIANTS[variant];

  return (
    <>
      <style>{PROTO_CSS}</style>
      <Component />
      {!import.meta.env.PROD && (
        <div className="proto-switcher">
          <button type="button" onClick={() => cycle(-1)} aria-label="Previous variant">
            ←
          </button>
          <span>
            {variant} — {name}
          </span>
          <button type="button" onClick={() => cycle(1)} aria-label="Next variant">
            →
          </button>
        </div>
      )}
    </>
  );
}

/* Scoped to `.proto-*` classes so nothing here can collide with real app CSS. */
const PROTO_CSS = `
.proto-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.2rem;
  border: none;
  background: transparent;
  color: var(--ink-soft);
  cursor: pointer;
  border-radius: 999px;
}
.proto-icon-btn:hover { color: var(--teal); background: var(--teal-pale); }
.proto-icon { width: 1.15rem; height: 1.15rem; }

.proto-popover-wrap { position: relative; display: inline-block; margin-left: 0.35rem; vertical-align: middle; }
.proto-popover {
  position: absolute;
  top: calc(100% + 0.6rem);
  left: 0;
  z-index: 30;
  width: 19rem;
  max-width: 80vw;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 0.6rem;
  padding: 0.85rem;
  box-shadow: 0 8px 24px rgba(18, 42, 46, 0.18);
}
.proto-popover-arrow {
  position: absolute;
  top: -0.4rem;
  left: 0.6rem;
  width: 0.75rem;
  height: 0.75rem;
  background: var(--card);
  border-left: 1px solid var(--line);
  border-top: 1px solid var(--line);
  transform: rotate(45deg);
}
.proto-popover-title { font-family: var(--font-display); font-weight: 600; margin: 0 0 0.5rem; }
.proto-steps {
  margin: 0 0 0.6rem;
  padding-left: 1.1rem;
  font-size: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
/* The global li selector (flex + justify-content: space-between, from the partner/invite
   row styling) otherwise bleeds into any plain ol/ul in the app — flex display on li also
   suppresses its marker per spec, so numbers vanish. Reset both back to normal here. */
.proto-steps li { display: list-item; justify-content: normal; padding: 0; border-bottom: none; }
.proto-copy-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0.6rem 0;
  padding: 0.4rem 0.5rem;
  border: 1px solid var(--line);
  border-radius: 0.4rem;
  background: var(--sand);
}
.proto-copy-row code { flex: 1; min-width: 0; overflow-x: auto; white-space: nowrap; font-size: 0.75rem; }
.proto-copy-row button { padding: 0.25rem 0.6rem; font-size: 0.75rem; flex-shrink: 0; }
.proto-unlocks { margin: 0; font-size: 0.78rem; }

.proto-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(18, 42, 46, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 40;
  padding: 1rem;
}
.proto-modal {
  width: 26rem;
  max-width: 100%;
  max-height: 85vh;
  overflow-y: auto;
  background: var(--card);
  border-radius: 0.85rem;
  padding: 1.25rem;
  box-shadow: 0 16px 48px rgba(18, 42, 46, 0.35);
}
.proto-modal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem; }
.proto-modal-header h3 { font-family: var(--font-display); margin: 0; }
.proto-modal-done { width: 100%; margin-top: 0.5rem; background: var(--teal); color: #fff; border-color: var(--teal); }

.proto-inline-section { border: 1px solid var(--line); border-radius: 0.6rem; margin-bottom: 1rem; overflow: hidden; }
.proto-inline-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 0.85rem;
  border: none;
  background: var(--card);
  color: var(--ink);
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
}
.proto-inline-row span { flex: 1; text-align: left; }
.proto-inline-body { padding: 0 0.85rem 0.85rem; border-top: 1px solid var(--line); padding-top: 0.75rem; }

.proto-switcher {
  position: fixed;
  bottom: 1.25rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 999;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.4rem 0.5rem;
  border-radius: 999px;
  background: #122a2e;
  color: #fff;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}
.proto-switcher button {
  border: none;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  width: 1.6rem;
  height: 1.6rem;
  border-radius: 999px;
  cursor: pointer;
  padding: 0;
}
.proto-switcher button:hover { background: rgba(255, 255, 255, 0.22); }
`;
