import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import {
  useNutritionCalendar,
  usePlannedWorkouts,
  useWorkoutHistory,
  useWorkoutStreak,
} from "../api/dashboard";
import { usePartnerSummary } from "../api/partner";
import type { components } from "../api/generated";
import { Card, KeyList, PageHero, Ring } from "../components/ui";
import {
  dateFromIso,
  formatInstant,
  isoDateInTz,
  isoFromDate,
  todayIsoInTz,
  useUserTimezone,
} from "../lib/datetime";

type NutritionCalendarDay = components["schemas"]["NutritionCalendarDayOut"];
type TrackableProgress = components["schemas"]["TrackableProgressOut"];
type PlannedWorkout = components["schemas"]["PlannedWorkoutOut"];
type Workout = components["schemas"]["WorkoutOut"];

const DOW = ["S", "M", "T", "W", "T", "F", "S"];
// The workout week widget has to line up with the backend's week boundary —
// celebrations.py::_week_bounds() uses `d.weekday()` (Python: Monday=0), i.e.
// Monday-Sunday weeks, not the calendar-grid's Sunday-first convention below.
const WEEK_DOW = ["M", "T", "W", "T", "F", "S", "S"];
const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const MACRO_COLORS: Record<string, string> = {
  protein_g: "var(--teal)",
  carbs_g: "var(--gold)",
  fat_g: "var(--plum)",
  fiber_g: "var(--coral)",
};

// Calendar-date anchors (month/week grid cells, "today") are local-midnight Dates
// whose Y/M/D already carry the user's zone — see `today` in DashboardPage. `isoDate`
// just reads those parts back out; instants get bucketed with `isoDateInTz` instead.
const isoDate = isoFromDate;

function isSameDate(a: Date, b: Date): boolean {
  return isoDate(a) === isoDate(b);
}

function startOfWeek(d: Date): Date {
  // Monday-based, matching celebrations.py::_week_bounds() (Python weekday(): Mon=0).
  const jsDay = d.getDay(); // JS: Sun=0
  const daysSinceMonday = (jsDay + 6) % 7;
  const start = new Date(d);
  start.setDate(start.getDate() - daysSinceMonday);
  return start;
}

function formatDayHeader(d: Date): string {
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function formatMacro(consumed: string, target: string | null, unit: string): string {
  const c = Math.round(Number(consumed));
  if (target === null) return `${c} ${unit}`;
  return `${c} / ${Math.round(Number(target))} ${unit}`;
}

function macroPercent(consumed: string, target: string | null): number {
  if (target === null || Number(target) <= 0) return 0;
  return Math.min((Number(consumed) / Number(target)) * 100, 100);
}

const TOOLTIP_MARGIN = 8;

/** Viewport-clamped, not container-clamped — `position: fixed` off the anchor's own
 * rect, so it can never run past the screen edge regardless of which grid column or
 * how tall the card is (a day with many logged workouts used to push the box off
 * both the top and bottom of the page). Flips below the cell when there's not
 * enough room above. */
function positionTooltip(anchor: HTMLElement, width: number): CSSProperties {
  const rect = anchor.getBoundingClientRect();
  const left = Math.max(
    TOOLTIP_MARGIN,
    Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - TOOLTIP_MARGIN),
  );
  const anchorAbove = rect.top > 220;
  return {
    display: "block",
    position: "fixed",
    left,
    width,
    ...(anchorAbove
      ? { top: rect.top - TOOLTIP_MARGIN, transform: "translateY(-100%)" }
      : { top: rect.bottom + TOOLTIP_MARGIN }),
  };
}

/** Hover shows it, moving off the cell hides it, a tap toggles it for touch.
 * Matches legacy ConsistencyCalendar's tooltip trigger behavior. */
function useDayTooltip(width: number) {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const cellRefs = useRef(new Map<string, HTMLElement>());
  const [style, setStyle] = useState<CSSProperties>({ display: "none" });

  useLayoutEffect(() => {
    if (!activeKey) {
      setStyle({ display: "none" });
      return;
    }
    const el = cellRefs.current.get(activeKey);
    if (!el) return;
    setStyle(positionTooltip(el, width));
  }, [activeKey, width]);

  function registerCell(key: string, el: HTMLElement | null) {
    if (el) cellRefs.current.set(key, el);
    else cellRefs.current.delete(key);
  }

  function cellProps(key: string) {
    return {
      ref: (el: HTMLElement | null) => registerCell(key, el),
      onMouseEnter: () => setActiveKey(key),
      onMouseLeave: () => setActiveKey((k) => (k === key ? null : k)),
      onClick: () => setActiveKey((k) => (k === key ? null : key)),
    };
  }

  return { activeKey, style, cellProps };
}

/** Real dashboard, folded in from the throwaway prototype at /prototype/dashboard
 * (see prototype/dashboard-streaks branch). Nutrition: a daily hit/miss calendar,
 * no streak badge (dropped per feedback — the calendar itself is enough). Workouts:
 * current week only, plus the streak badge (kept — "I'm okay with the banner").
 * Both surface a hover/tap detail of what actually happened that day, matching the
 * legacy ConsistencyCalendar tooltip. */
export function DashboardPage() {
  const tz = useUserTimezone();
  // A local-midnight anchor whose Y/M/D is *today in the user's zone* — every
  // calendar computation below is date-only arithmetic hung off this.
  const today = useMemo(() => dateFromIso(todayIsoInTz(tz)), [tz]);
  const monthStart = useMemo(
    () => new Date(today.getFullYear(), today.getMonth(), 1),
    [today],
  );
  const monthEnd = useMemo(
    () => new Date(today.getFullYear(), today.getMonth() + 1, 0),
    [today],
  );
  const weekStart = useMemo(() => startOfWeek(today), [today]);
  const weekEnd = useMemo(() => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + 6);
    return d;
  }, [weekStart]);

  const calendar = useNutritionCalendar(isoDate(monthStart), isoDate(monthEnd));
  const planned = usePlannedWorkouts(isoDate(weekStart), isoDate(weekEnd));
  const history = useWorkoutHistory(isoDate(weekStart), isoDate(weekEnd));
  const streak = useWorkoutStreak();

  const todayNutrition = calendar.data?.find((d) => d.date === isoDate(today));
  const todaysPlan = planned.data?.find(
    (p) => p.scheduled_for === isoDate(today) && p.status === "planned",
  );

  return (
    <>
      <PageHero
        eyebrow={today.toLocaleDateString(undefined, {
          weekday: "long",
          day: "numeric",
          month: "long",
        })}
        title={heroTitle(todayNutrition, streak.data)}
        lead={heroLead(todayNutrition, todaysPlan?.template_name ?? null)}
        actions={
          <>
            <a className="btn--primary" href="/workouts/live">
              {todaysPlan ? `Start ${todaysPlan.template_name}` : "Start a workout"}
            </a>
            <a className="btn--ghost" href="/nutrition">
              Log food
            </a>
          </>
        }
        aside={<HeroRings day={todayNutrition} streak={streak.data} />}
      />

      <div className="page-body">
        <div className="page-grid page-grid--three">
          {calendar.isPending && <p className="muted">Loading nutrition…</p>}
          {calendar.isError && <p className="error">Couldn’t load the nutrition calendar.</p>}
          {calendar.data && (
            <NutritionCalendarCard days={calendar.data} today={today} monthStart={monthStart} />
          )}

          {(planned.isPending || history.isPending || streak.isPending) && (
            <p className="muted">Loading workouts…</p>
          )}
          {(planned.isError || history.isError || streak.isError) && (
            <p className="error">Couldn’t load this week’s workouts.</p>
          )}
          {planned.data && history.data && streak.data && (
            <WorkoutWeekCard
              planned={planned.data}
              workouts={history.data}
              streak={streak.data}
              weekStart={weekStart}
              today={today}
            />
          )}

          <SwolemateCard mine={streak.data ?? null} />
        </div>
      </div>
    </>
  );
}

/** The partner column from the mockup. Only aggregates cross this boundary — see
 *  PartnerSummaryOut — so this shows their week against yours and nothing more. */
function SwolemateCard({ mine }: { mine: Streak | null }) {
  const summary = usePartnerSummary();
  const tz = useUserTimezone();

  if (summary.isPending || summary.isError) return null;
  if (!summary.data) {
    return (
      <Card title="Swolemate">
        <p className="card-note">
          No partner yet. <a href="/partner">Invite one</a> and their week shows up here.
        </p>
      </Card>
    );
  }

  const partner = summary.data;
  const name = partner.partner_display_name ?? "Your partner";
  const theirs = partner.streak.this_week;
  const gap = mine === null ? null : theirs - mine.this_week;

  return (
    <Card title="Swolemate">
      <div className="partner-head">
        <span className="partner-avatar">{initials(name)}</span>
        <div>
          <div className="partner-name">{name}</div>
          <div className="partner-sub">
            {theirs} of {partner.streak.target}
            {partner.frequency.last_workout_at
              ? ` · ${formatInstant(partner.frequency.last_workout_at, tz)}`
              : " · nothing logged yet"}
          </div>
        </div>
      </div>
      <p className="card-note">
        {gap === null || gap === 0
          ? "You’re level on the week."
          : gap > 0
            ? `${gap} ahead of you this week.`
            : `${-gap} behind you this week.`}{" "}
        {partner.streak.weeks}-week streak.
      </p>
      <a className="btn--ghost partner-action" href="/partner">
        See {name.split(" ")[0]}
      </a>
    </Card>
  );
}

/** "Maya Reyes" → "MR"; a single word falls back to its first two letters. */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0];
  const last = parts[parts.length - 1];
  if (first === undefined || last === undefined) return "?";
  if (parts.length === 1) return first.slice(0, 2).toUpperCase();
  return `${first[0]}${last[0]}`.toUpperCase();
}

/** The directive: whichever of "eat" or "lift" still has ground to cover today. */
function heroTitle(day: NutritionCalendarDay | undefined, streak: Streak | undefined): string {
  const kcalLeft = day ? remaining(day.hero) : null;
  const liftsLeft = streak ? Math.max(streak.target - streak.this_week, 0) : null;
  const parts: string[] = [];
  if (kcalLeft !== null && kcalLeft > 0) {
    parts.push(`${Math.round(kcalLeft).toLocaleString()} ${day!.hero.unit} left`);
  }
  if (liftsLeft) parts.push(`${liftsLeft} ${liftsLeft === 1 ? "workout" : "workouts"} to go`);
  if (parts.length === 0) return "You’re on target for the week.";
  return `${parts.join(" and ")}.`;
}

function heroLead(day: NutritionCalendarDay | undefined, plan: string | null): string {
  const protein = day?.bars.find((b) => b.trackable_key === "protein_g");
  const proteinLeft = protein ? remaining(protein) : null;
  const food =
    proteinLeft === null
      ? "No targets set yet — the Profile tab can work them out for you."
      : proteinLeft > 0
        ? `Protein is ${Math.round(proteinLeft)} ${protein!.unit} short.`
        : "Every macro is where it should be.";
  return plan ? `${food} ${plan} is on the plan for today.` : `${food} Nothing planned today.`;
}

function remaining(p: TrackableProgress): number | null {
  if (p.target === null) return null;
  return Number(p.target) - Number(p.consumed);
}

function fraction(p: TrackableProgress | undefined): number {
  if (!p || p.target === null || Number(p.target) <= 0) return 0;
  return Number(p.consumed) / Number(p.target);
}

/** Calories, protein and the week — the three dials the mockup opens with. */
function HeroRings({
  day,
  streak,
}: {
  day: NutritionCalendarDay | undefined;
  streak: Streak | undefined;
}) {
  const protein = day?.bars.find((b) => b.trackable_key === "protein_g");
  const percent = (p: TrackableProgress | undefined) => `${Math.round(fraction(p) * 100)}%`;
  return (
    <div className="hero-rings">
      <Ring
        label="Calories"
        value={percent(day?.hero)}
        sub={day ? Math.round(Number(day.hero.consumed)).toLocaleString() : "—"}
        fraction={fraction(day?.hero)}
        color="var(--teal)"
      />
      <Ring
        label="Protein"
        value={percent(protein)}
        sub={protein ? `${Math.round(Number(protein.consumed))} ${protein.unit}` : "—"}
        fraction={fraction(protein)}
        color="var(--coral)"
      />
      <Ring
        label="Week"
        value={streak ? `${streak.this_week}/${streak.target}` : "—"}
        sub="lifts"
        fraction={streak && streak.target > 0 ? streak.this_week / streak.target : 0}
        color="var(--plum)"
      />
    </div>
  );
}

function NutritionCalendarCard({
  days,
  today,
  monthStart,
}: {
  days: NutritionCalendarDay[];
  today: Date;
  monthStart: Date;
}) {
  const byDate = useMemo(() => new Map(days.map((d) => [d.date, d])), [days]);
  const { activeKey, style, cellProps } = useDayTooltip(192);
  const activeDay = activeKey ? byDate.get(activeKey) : undefined;
  const activeDate = activeKey ? dateFromIso(activeKey) : null;

  const firstDow = monthStart.getDay();
  const daysInMonth = new Date(monthStart.getFullYear(), monthStart.getMonth() + 1, 0).getDate();
  const cells: (Date | null)[] = [
    ...Array<null>(firstDow).fill(null),
    ...Array.from(
      { length: daysInMonth },
      (_, i) => new Date(monthStart.getFullYear(), monthStart.getMonth(), i + 1),
    ),
  ];

  return (
    <Card title={`${MONTH_NAMES[monthStart.getMonth()]} ${monthStart.getFullYear()}`}>
      <div className="dash-grid">
        {DOW.map((d, i) => (
          <div key={i} className="dash-dow">{d}</div>
        ))}
        {cells.map((date, i) => {
          if (date === null) return <div key={i} />;
          const key = isoDate(date);
          const day = byDate.get(key);
          const isFuture = date > today && !isSameDate(date, today);
          const isToday = isSameDate(date, today);
          const status = day?.status ?? "no-data";
          const interactive = day !== undefined && !isFuture;
          return (
            <div key={i} className="dash-cell-wrap" {...(interactive ? cellProps(key) : {})}>
              <div
                className={`dash-cell dash-cell--${status}${isToday ? " dash-cell--today" : ""}${interactive ? " dash-cell--interactive" : ""}`}
              >
                {date.getDate()}
              </div>
            </div>
          );
        })}
      </div>
      <KeyList
        items={[
          { swatch: { background: "var(--teal)" }, text: "Hit your calorie goal" },
          { swatch: { background: "var(--coral-pale)" }, text: "Missed it" },
          { swatch: { background: "var(--sand)" }, text: "Nothing logged" },
        ]}
      />
      {activeDay && activeDate && (
        <div className="dash-tooltip" role="tooltip" style={style}>
          <div className="dash-tooltip-date">{formatDayHeader(activeDate)}</div>
          {activeDay.status === "no-data" ? (
            <div className="dash-tooltip-empty">Nothing logged</div>
          ) : (
            <>
              <div className="dash-tooltip-hero">
                {formatMacro(activeDay.hero.consumed, activeDay.hero.target, activeDay.hero.unit)}
              </div>
              <div className="dash-tooltip-bars">
                {activeDay.bars.map((bar) => (
                  <div key={bar.trackable_key} className="dash-tooltip-bar">
                    <div className="dash-tooltip-bar-label">
                      <span>{bar.label}</span>
                      <span>{formatMacro(bar.consumed, bar.target, bar.unit)}</span>
                    </div>
                    {/* Always rendered, even with no target (0% fill) — matches
                        nutrition-day.html's bar-track, which never hides the track
                        either. Hiding it here made an unset goal look like a rendering
                        bug rather than "no goal set yet". */}
                    <div className="dash-tooltip-bar-track">
                      <div
                        className="dash-tooltip-bar-fill"
                        style={{
                          width: `${macroPercent(bar.consumed, bar.target)}%`,
                          background: MACRO_COLORS[bar.trackable_key] ?? "var(--ink-soft)",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </Card>
  );
}

type WeekDayStatus = "done" | "skipped" | "upcoming" | "rest";
type Streak = components["schemas"]["StreakOut"];

function WorkoutWeekCard({
  planned,
  workouts,
  streak,
  weekStart,
  today,
}: {
  planned: PlannedWorkout[];
  workouts: Workout[];
  streak: Streak;
  weekStart: Date;
  today: Date;
}) {
  const { activeKey, style, cellProps } = useDayTooltip(168);
  const tz = useUserTimezone();

  const plannedByDate = useMemo(() => {
    const map = new Map<string, PlannedWorkout>();
    for (const p of planned) if (!map.has(p.scheduled_for)) map.set(p.scheduled_for, p);
    return map;
  }, [planned]);

  const completedByDate = useMemo(() => {
    const map = new Map<string, Workout[]>();
    for (const w of workouts) {
      if (!w.completed_at) continue;
      const key = isoDateInTz(w.completed_at, tz);
      const list = map.get(key) ?? [];
      list.push(w);
      map.set(key, list);
    }
    return map;
  }, [workouts, tz]);

  const weekInfo = Array.from({ length: 7 }, (_, i) => {
    const date = new Date(weekStart);
    date.setDate(date.getDate() + i);
    const key = isoDate(date);
    const isToday = isSameDate(date, today);
    const isPast = date < today && !isToday;
    const done = completedByDate.get(key) ?? [];
    const plannedEntry = plannedByDate.get(key);

    let status: WeekDayStatus;
    if (done.length > 0) status = "done";
    else if (plannedEntry) status = isPast || isToday ? "skipped" : "upcoming";
    else status = "rest";

    return { date, key, isToday, done, plannedEntry, status };
  });
  const active = activeKey ? weekInfo.find((d) => d.key === activeKey) : undefined;

  return (
    <Card
      title="This week’s workouts"
      meta={<span className="badge badge--plum">{streak.weeks}-week streak</span>}
    >
      <div className="dash-week-row">
        {weekInfo.map(({ date, key, isToday, status, done, plannedEntry }, i) => {
          // A logged day keeps its "done" fill even when it's today — the key
          // reads today's tile as "planned", which a finished workout isn't.
          const skin = isToday && status !== "done" ? "today" : status;
          return (
            <div key={key} className="dash-week-daycell" {...cellProps(key)}>
              <span className="dash-week-dow">{WEEK_DOW[i]}</span>
              <div className={`dash-week-daynum dash-week-daynum--${skin}`}>
                {date.getDate()}
                <span className="dash-week-tag">
                  {done[0]
                    ? (done[0].title ?? "workout")
                    : (plannedEntry?.template_name ?? "rest")}
                </span>
              </div>
            </div>
          );
        })}
      </div>
      <KeyList
        items={[
          { swatch: { background: "var(--plum)" }, text: "Logged a workout" },
          { swatch: { background: "var(--teal)" }, text: "Today, planned" },
          {
            swatch: { background: "var(--card)", border: "1px dashed var(--plum)" },
            text: "Planned, still ahead",
          },
          {
            swatch: { background: "var(--sand)", border: "1px solid var(--line-soft)" },
            text: "Rest or nothing planned",
          },
        ]}
      />
      <p className="card-note">
        <strong>{streak.this_week} of {streak.target}</strong> workouts this week — any day counts,
        a skipped plan doesn’t break the streak if you make it up before Sunday
      </p>
      {active && (
        <div className="dash-tooltip dash-tooltip--week" role="tooltip" style={style}>
          <div className="dash-tooltip-date">{formatDayHeader(active.date)}</div>
          {active.done.length > 0 ? (
            active.done.map((w) => (
              <div key={w.id} className="dash-tooltip-workout">
                <strong>
                  {w.title ??
                    (w.workout_type === "strength" ? "Strength workout" : (w.activity_type ?? "Workout"))}
                </strong>
                {w.exercises.length > 0 && (
                  <div className="dash-tooltip-empty">
                    {w.exercises.map((e) => e.exercise_name).filter(Boolean).join(", ")}
                  </div>
                )}
                {w.duration_minutes !== null && (
                  <div className="dash-tooltip-empty">{w.duration_minutes} min</div>
                )}
              </div>
            ))
          ) : active.plannedEntry ? (
            <div className="dash-tooltip-workout">
              <strong>Planned: {active.plannedEntry.template_name}</strong>
              {active.plannedEntry.exercise_names.length > 0 && (
                <div className="dash-tooltip-empty">
                  {active.plannedEntry.exercise_names.join(", ")}
                </div>
              )}
              <div className="dash-tooltip-empty">
                {active.status === "skipped"
                  ? "Skipped — doesn’t break your streak if you make it up"
                  : "Coming up"}
              </div>
            </div>
          ) : (
            <div className="dash-tooltip-empty">Nothing planned</div>
          )}
        </div>
      )}
    </Card>
  );
}
