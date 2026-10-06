/**
 * Which day the card is showing, and how a tool call is told about it.
 *
 * Split out of `main.ts` — which is a DOM side-effect bundle and can't be imported by
 * a test — for the same reason `mealType.ts` and workout-live's `prefill.ts` are: the
 * date arithmetic here is the part that's actually easy to get wrong, and this is the
 * bug class where getting it wrong means food quietly lands on the wrong day.
 */

/** `YYYY-MM-DD` in the viewer's own zone. Read off the local getters rather than
 *  `toISOString()`, which converts to UTC first — that hands anyone west of Greenwich
 *  tomorrow's date for most of their evening, which is the exact class of bug this
 *  whole feature is about. */
export function isoOf(d: Date): string {
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

export const todayIso = (): string => isoOf(new Date());

/** Noon, so adding a day can't land on a DST hour that doesn't exist locally. */
export function shiftIso(iso: string, days: number): string {
  const shifted = new Date(`${iso}T12:00:00`);
  shifted.setDate(shifted.getDate() + days);
  return isoOf(shifted);
}

/** "Today", "Yesterday", or "Mon 7 Sep" — a bare date is hard to place at a glance,
 *  and placing it is the whole job of this header when the card isn't today's. */
export function dayLabel(iso: string, today = todayIso()): string {
  if (iso === today) return "Today";
  if (iso === shiftIso(today, -1)) return "Yesterday";
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

/**
 * Tools whose `date` means "the day this call concerns", so the viewed day can be
 * filled in for them. Two deliberate absences:
 *
 *  - `search_food_facts` has no `date` at all — an unknown argument is a tool error.
 *  - `update_nutrition_log`'s `date` *moves* the entry. Filling it in from the view
 *    would re-time every meal-type edit on a past day to noon, silently, which is a
 *    worse bug than the one this fixes. The SPA host tracks the viewed day itself for
 *    the refetch after an edit; chat re-reads on its own.
 */
export const DAY_SCOPED_TOOLS = new Set([
  "get_nutrition_day",
  "log_nutrition",
  "log_meal_template",
  "save_meal_template",
  "update_meal_template",
  "update_meal_template_item",
  "delete_meal_template",
  "delete_nutrition_log",
]);

/**
 * The arguments to actually send. Every day-scoped tool defaults to today when it
 * isn't told otherwise — so a call made while looking at a past day has to say which
 * day, or the write lands on today and the card that comes back snaps away from what
 * the user was reading. Filled in here rather than at each of the dozen call sites,
 * which is exactly where it would get forgotten.
 *
 * `viewed` is null when the card is already on today, so the default path sends
 * exactly what it always sent — and a component left open overnight rolls forward
 * instead of pinning itself to yesterday. An explicit `date` in `args` always wins.
 */
export function withViewedDay(
  name: string,
  args: Record<string, unknown>,
  viewed: string | null,
): Record<string, unknown> {
  if (viewed === null || !DAY_SCOPED_TOOLS.has(name) || "date" in args) return args;
  return { ...args, date: viewed };
}
