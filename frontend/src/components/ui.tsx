import type { CSSProperties, ReactNode } from "react";

/**
 * The handful of shapes every page in the redesign is built from. Nothing here
 * holds state or fetches — they exist so the hero band, the cards and the rings
 * read identically on Today, Nutrition and Workout.
 */

/** The band a page opens with: a mono eyebrow, the directive as a display-face
 *  headline, a supporting line, then actions. `aside` carries rings or stats. */
export function PageHero({
  eyebrow,
  title,
  lead,
  actions,
  aside,
  below,
}: {
  eyebrow: string;
  title: string;
  lead?: ReactNode;
  actions?: ReactNode;
  /** Sits to the right of the directive — rings, stats. */
  aside?: ReactNode;
  /** Spans the full band under the directive — the Plan tab's day grid. */
  below?: ReactNode;
}) {
  return (
    <header className="page-hero">
      <div className="page-hero-inner">
        <div className="page-hero-main">
          <p className="hero-eyebrow">{eyebrow}</p>
          <h2 className="hero-title">{title}</h2>
          {lead && <p className="hero-lead">{lead}</p>}
          {actions && <div className="hero-actions">{actions}</div>}
        </div>
        {aside}
        {below && <div className="page-hero-below">{below}</div>}
      </div>
    </header>
  );
}

export function Card({
  title,
  meta,
  children,
}: {
  title?: ReactNode;
  /** Right-hand note in the header — a count, a range, a badge. */
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      {(title || meta) && (
        <div className="card-header">
          {title && <span className="card-title">{title}</span>}
          {meta}
        </div>
      )}
      {children}
    </section>
  );
}

/** Conic-gradient dial. The hole is painted with the hero band's background, so
 *  a ring only reads correctly inside a `PageHero`. */
export function Ring({
  label,
  value,
  sub,
  fraction,
  color,
}: {
  label: string;
  value: string;
  sub: string;
  /** 0–1, clamped. */
  fraction: number;
  color: string;
}) {
  const turns = Math.max(0, Math.min(fraction, 1));
  const style: CSSProperties = {
    background: `conic-gradient(${color} 0turn ${turns}turn, var(--line-soft) ${turns}turn 1turn)`,
  };
  return (
    <div>
      <div className="ring" style={style}>
        <div className="ring-hole">
          <div>
            <div className="ring-value">{value}</div>
            <div className="ring-sub">{sub}</div>
          </div>
        </div>
      </div>
      <span className="ring-label">{label}</span>
    </div>
  );
}

export type KeyItem = { swatch: CSSProperties; text: string };

/** Spells each state out in words instead of leaving a row of bare swatches. */
export function KeyList({ items }: { items: KeyItem[] }) {
  return (
    <div className="key-list">
      {items.map((item) => (
        <div key={item.text} className="key-row">
          <span className="key-swatch" style={item.swatch} />
          {item.text}
        </div>
      ))}
    </div>
  );
}
