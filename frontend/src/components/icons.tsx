/** Icons — from lucide.dev (ISC license), used as-is. Each inherits color from
 *  its parent via `currentColor` (the source SVGs already set `stroke="currentColor"`),
 *  so the surrounding hover/active color rules apply with no icon-specific CSS. */

type IconProps = { className?: string };

const iconProps = {
  xmlns: "http://www.w3.org/2000/svg",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function InfoIcon({ className }: IconProps) {
  return (
    <svg {...iconProps} className={className}>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4" />
      <path d="M12 8h.01" />
    </svg>
  );
}
