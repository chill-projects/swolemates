import {
  macroPercent,
  remainingOf,
  type DayTotals,
  type NutritionTargets,
} from "@/lib/tdee";

const RING_SIZE = 168;
const RING_STROKE = 14;
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

const MACRO_BARS: {
  key: "protein" | "carbs" | "fat" | "fiber";
  label: string;
  color: string;
}[] = [
  { key: "protein", label: "Protein", color: "bg-teal" },
  { key: "carbs", label: "Carbs", color: "bg-gold" },
  { key: "fat", label: "Fat", color: "bg-plum" },
  { key: "fiber", label: "Fiber", color: "bg-coral" },
];

type Remaining = {
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
  fiber: number;
};

// Deterministic, no API call — just surfaces whichever macro is closest to
// done but not yet there, favoring protein since that's the one worth a
// deliberate top-up; falls back to a generic "you're clear" message.
function dailyTip(remaining: Remaining): { bold: string; rest: string } {
  if (remaining.protein > 0 && remaining.protein <= 25) {
    return {
      bold: "Almost there on protein",
      rest: ` — ${remaining.protein}g left. A Greek yogurt cup or a handful of jerky closes it easily.`,
    };
  }
  if (remaining.fiber > 0 && remaining.fiber <= 10) {
    return {
      bold: "Almost there on fiber",
      rest: ` — ${remaining.fiber}g left. Berries or a handful of nuts closes the gap.`,
    };
  }
  if (remaining.calories <= 0 && remaining.protein <= 0) {
    return {
      bold: "Nice work today",
      rest: " — you've hit your calorie and protein targets.",
    };
  }
  if (remaining.protein > 25) {
    return {
      bold: "Protein still has room",
      rest: ` — ${remaining.protein}g left. A chicken breast or a protein shake gets you most of the way there.`,
    };
  }
  return {
    bold: "Plenty of room left",
    rest: ` — ${remaining.calories} calories left today for a balanced meal.`,
  };
}

export function TodaySummary({
  totals,
  targets,
}: {
  totals: DayTotals;
  targets: NutritionTargets | null;
}) {
  const pct = targets ? Math.min(totals.calories / targets.calories, 1) : 0;
  const dashOffset = RING_CIRCUMFERENCE * (1 - pct);

  const remaining: Remaining | null = targets
    ? {
        calories: remainingOf(totals.calories, targets.calories),
        protein: remainingOf(totals.protein, targets.protein),
        carbs: remainingOf(totals.carbs, targets.carbs),
        fat: remainingOf(totals.fat, targets.fat),
        fiber: remainingOf(totals.fiber, targets.fiber),
      }
    : null;
  const tip = remaining ? dailyTip(remaining) : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-2xl border border-line bg-card p-5">
        <div className="flex items-center gap-6">
          <div
            className="grid shrink-0 place-items-center"
            style={{ width: RING_SIZE, height: RING_SIZE }}
          >
            <svg
              width={RING_SIZE}
              height={RING_SIZE}
              className="col-start-1 row-start-1 -rotate-90"
            >
              <circle
                cx={RING_SIZE / 2}
                cy={RING_SIZE / 2}
                r={RING_RADIUS}
                fill="none"
                stroke="var(--sand)"
                strokeWidth={RING_STROKE}
              />
              {targets && (
                <circle
                  cx={RING_SIZE / 2}
                  cy={RING_SIZE / 2}
                  r={RING_RADIUS}
                  fill="none"
                  stroke="var(--teal)"
                  strokeWidth={RING_STROKE}
                  strokeLinecap="round"
                  strokeDasharray={RING_CIRCUMFERENCE}
                  strokeDashoffset={dashOffset}
                />
              )}
            </svg>
            <div className="col-start-1 row-start-1 flex flex-col items-center justify-center">
              <span className="font-display text-4xl font-semibold leading-none">
                {Math.round(totals.calories).toLocaleString()}
              </span>
              {targets && (
                <span className="mt-1 font-mono text-xs text-ink-soft">
                  / {targets.calories.toLocaleString()}
                </span>
              )}
              <span className="mt-1 font-mono text-[11px] font-semibold tracking-wide text-teal uppercase">
                Calories
              </span>
            </div>
          </div>

          <div className="flex flex-1 flex-col gap-3">
            <div className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
              Macros
            </div>
            {MACRO_BARS.map(({ key, label, color }) => {
              const value = totals[key];
              const target = targets?.[key];
              const pctBar = macroPercent(value, target);
              return (
                <div key={key}>
                  <div className="flex items-baseline justify-between">
                    <span className="font-semibold">{label}</span>
                    <span className="font-mono text-sm text-ink-soft">
                      {Math.round(value)}
                      {target ? ` / ${Math.round(target)}g` : "g"}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-sand">
                    <div
                      className={`h-full rounded-full ${color}`}
                      style={{ width: `${pctBar}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {targets && remaining && tip && (
        <div className="rounded-2xl bg-teal p-5 text-white">
          <div className="font-mono text-[11px] tracking-wide text-white/70 uppercase">
            You have left today
          </div>
          <div className="mt-3 grid grid-cols-5 gap-2 text-center">
            {[
              { value: remaining.protein, label: "Protein", suffix: "g" },
              { value: remaining.carbs, label: "Carbs", suffix: "g" },
              { value: remaining.fat, label: "Fat", suffix: "g" },
              { value: remaining.calories, label: "Calories", suffix: "" },
              { value: remaining.fiber, label: "Fiber", suffix: "g" },
            ].map(({ value, label, suffix }) => (
              <div key={label}>
                <div className="font-display text-2xl font-semibold">
                  {value}
                  {suffix}
                </div>
                <div className="mt-0.5 font-mono text-[10px] tracking-wide text-white/70 uppercase">
                  {label}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-xl border-l-4 border-coral bg-white/10 px-4 py-3 text-sm">
            <span className="font-semibold">{tip.bold}</span>
            {tip.rest}
          </div>
        </div>
      )}
    </div>
  );
}
