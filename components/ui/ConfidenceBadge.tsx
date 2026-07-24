type ConfidenceLevel = "low" | "medium" | "high";

const STYLES: Record<ConfidenceLevel, string> = {
  high: "bg-teal-pale text-teal",
  medium: "bg-gold-pale text-amber",
  low: "bg-coral-pale text-red",
};

export function ConfidenceBadge({
  level,
  hideHigh = false,
}: {
  level: ConfidenceLevel;
  hideHigh?: boolean;
}) {
  if (hideHigh && level === "high") return null;

  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 font-mono text-[10px] tracking-wide uppercase ${STYLES[level]}`}
    >
      {level} confidence
    </span>
  );
}
