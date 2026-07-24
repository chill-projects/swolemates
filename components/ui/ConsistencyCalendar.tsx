"use client";

import { useRef, useState } from "react";
import {
  dateKeyFromParts,
  dayStatus,
  macroPercent,
  type DayTotals,
  type GoalType,
  type NutritionTargets,
} from "@/lib/tdee";

const DOW = ["S", "M", "T", "W", "T", "F", "S"];
const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const MACRO_BARS: {
  key: keyof DayTotals;
  label: string;
  color: string;
}[] = [
  { key: "protein", label: "Protein", color: "bg-teal" },
  { key: "carbs", label: "Carbs", color: "bg-gold" },
  { key: "fat", label: "Fat", color: "bg-plum" },
  { key: "fiber", label: "Fiber", color: "bg-coral" },
];

export function ConsistencyCalendar({
  year,
  month, // 0-indexed
  dailyTotals,
  streakDays,
  targets,
  goalType,
}: {
  year: number;
  month: number;
  dailyTotals: Record<string, DayTotals>;
  streakDays: number;
  targets: NutritionTargets | null;
  goalType: GoalType | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<{
    key: string;
    left: number;
    top: number;
  } | null>(null);

  const firstDow = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const now = new Date();
  const todayKey = dateKeyFromParts(now.getFullYear(), now.getMonth(), now.getDate());

  const cells: (number | null)[] = [
    ...Array(firstDow).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  function showTooltip(key: string, cellEl: HTMLElement) {
    const container = containerRef.current;
    if (!container) return;
    const containerRect = container.getBoundingClientRect();
    const cellRect = cellEl.getBoundingClientRect();

    const tooltipWidth = 208; // matches the w-52 tooltip below
    let left = cellRect.left - containerRect.left + cellRect.width / 2 - tooltipWidth / 2;
    left = Math.max(4, Math.min(left, containerRect.width - tooltipWidth - 4));
    const top = cellRect.top - containerRect.top - 8;

    setActive({ key, left, top });
  }

  const activeTotals = active ? dailyTotals[active.key] : null;

  return (
    <div ref={containerRef} className="relative">
      <div className="flex items-center justify-between">
        <div className="font-display text-base font-semibold">
          {MONTH_NAMES[month]} {year}
        </div>
        <span className="rounded-full bg-teal-pale px-2.5 py-1 font-mono text-[11px] text-teal">
          {streakDays}-day streak
        </span>
      </div>

      <div className="mt-3 grid grid-cols-[repeat(7,minmax(0,1fr))] gap-1.5">
        {DOW.map((d, i) => (
          <div
            key={i}
            className="text-center font-mono text-[10px] text-ink-soft uppercase"
          >
            {d}
          </div>
        ))}
        {cells.map((day, i) => {
          if (day === null) return <div key={`empty-${i}`} />;

          const key = dateKeyFromParts(year, month, day);
          const totals = dailyTotals[key];
          const status = dayStatus(totals, targets, goalType);
          const isToday = key === todayKey;
          const isActive = key === active?.key;

          return (
            <button
              key={key}
              type="button"
              onClick={(e) =>
                isActive ? setActive(null) : showTooltip(key, e.currentTarget)
              }
              onMouseEnter={(e) => showTooltip(key, e.currentTarget)}
              onMouseLeave={() => setActive((prev) => (prev?.key === key ? null : prev))}
              disabled={status === "no-data"}
              className={`aspect-square rounded-lg font-mono text-xs transition-transform ${
                status === "hit"
                  ? "bg-teal font-semibold text-white"
                  : status === "miss"
                    ? "bg-coral-pale text-red"
                    : "bg-sand text-ink-soft"
              } ${isToday ? "ring-2 ring-teal ring-offset-1 ring-offset-card" : ""} ${
                isActive ? "scale-90" : ""
              } ${status !== "no-data" ? "cursor-pointer" : "cursor-default"}`}
            >
              {day}
            </button>
          );
        })}
      </div>

      {active && activeTotals && (
        <div
          className="absolute z-10 w-52 -translate-y-full rounded-xl bg-ink px-4 py-3 text-white shadow-lg"
          style={{ left: active.left, top: active.top }}
        >
          <div className="font-mono text-[10px] tracking-wide text-white/60 uppercase">
            {new Date(`${active.key}T00:00:00`).toLocaleDateString(undefined, {
              weekday: "short",
              month: "short",
              day: "numeric",
            })}
          </div>
          <div className="mt-0.5 font-display text-xl font-semibold">
            {Math.round(activeTotals.calories)}
            {targets && (
              <span className="ml-1 font-mono text-xs font-normal text-white/60">
                / {targets.calories} cal
              </span>
            )}
          </div>

          <div className="mt-2 flex flex-col gap-1.5">
            {MACRO_BARS.map(({ key: macroKey, label, color }) => {
              const value = activeTotals[macroKey];
              const target = targets?.[macroKey];
              const pct = macroPercent(value, target);
              return (
                <div key={macroKey}>
                  <div className="flex justify-between font-mono text-[10px] text-white/70">
                    <span>{label}</span>
                    <span>
                      {Math.round(value)}
                      {target ? `/${target}g` : "g"}
                    </span>
                  </div>
                  {target && (
                    <div className="mt-0.5 h-1 rounded-full bg-white/15">
                      <div
                        className={`h-full rounded-full ${color}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="mt-3 flex gap-4 font-mono text-[11px] text-ink-soft">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-teal" />
          {targets ? "Hit goal" : "Logged"}
        </span>
        {targets && (
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-coral-pale" />
            Missed
          </span>
        )}
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-sand" /> No data
        </span>
      </div>
    </div>
  );
}
