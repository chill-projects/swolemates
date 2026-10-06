/**
 * Meal-plan helpers, kept out of the components so they're testable without a DOM.
 *
 * The only subtle one is `dayMacros`. A planned meal whose macros nobody knows is not
 * zero calories, so it is excluded from the total and counted separately — a day that
 * silently under-reports is worse than one that admits it doesn't know.
 */

export const MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"] as const;
export type MealType = (typeof MEAL_TYPES)[number];

export interface PlannedMealLike {
  meal_type: string;
  values: Record<string, string>;
  estimated: boolean;
}

/** Monday-first, matching the weekly workout pattern's own day numbering. */
export function weekStart(day: Date): Date {
  const copy = new Date(day.getFullYear(), day.getMonth(), day.getDate());
  const weekday = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - weekday);
  return copy;
}

export function isoDate(day: Date): string {
  const month = String(day.getMonth() + 1).padStart(2, "0");
  const date = String(day.getDate()).padStart(2, "0");
  return `${day.getFullYear()}-${month}-${date}`;
}

export function addDays(day: Date, count: number): Date {
  const copy = new Date(day);
  copy.setDate(copy.getDate() + count);
  return copy;
}

/** The seven ISO dates of the week containing `day`. */
export function weekDates(day: Date): string[] {
  const start = weekStart(day);
  return Array.from({ length: 7 }, (_, i) => isoDate(addDays(start, i)));
}

/** "Mon 28 Sep" — short enough for a 142px column. */
export function dayLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y!, m! - 1, d!);
  return date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

export function slotOrder(mealType: string): number {
  const index = (MEAL_TYPES as readonly string[]).indexOf(mealType);
  return index === -1 ? MEAL_TYPES.length : index;
}

export function sortBySlot<T extends { meal_type: string }>(meals: T[]): T[] {
  return [...meals].sort((a, b) => slotOrder(a.meal_type) - slotOrder(b.meal_type));
}

export interface DayMacros {
  calories: number;
  protein: number;
  /** Meals whose macros nobody knows. The totals above exclude them. */
  unestimated: number;
}

export function dayMacros(meals: PlannedMealLike[]): DayMacros {
  return meals.reduce<DayMacros>(
    (acc, meal) => {
      if (!meal.estimated) {
        acc.unestimated += 1;
        return acc;
      }
      acc.calories += Number(meal.values.calories ?? 0);
      acc.protein += Number(meal.values.protein_g ?? 0);
      return acc;
    },
    { calories: 0, protein: 0, unestimated: 0 },
  );
}

/** What a slot shows under the meal name: its own numbers, or an honest blank. */
export function macroLabel(meal: PlannedMealLike): string {
  if (!meal.estimated) return "not estimated";
  const kcal = Math.round(Number(meal.values.calories ?? 0));
  const protein = Math.round(Number(meal.values.protein_g ?? 0));
  return `${kcal.toLocaleString()} kcal · ${protein} g`;
}

/** Strips the trailing zeros a portion multiply leaves behind, for edit fields. */
export function tidyNumber(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return String(Math.round(n * 100) / 100);
}

/** Only the trackables the planner edits, in a stable order. */
export const EDITABLE_TRACKABLES = ["calories", "protein_g", "carbs_g", "fat_g"] as const;

export const TRACKABLE_LABELS: Record<string, string> = {
  calories: "kcal",
  protein_g: "protein",
  carbs_g: "carbs",
  fat_g: "fat",
};

/** Turn the edit form's strings into the API's shape, dropping the blanks.
 *  An entirely blank form means "clear the override", which the API spells `{}`. */
export function macrosFromForm(form: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of EDITABLE_TRACKABLES) {
    const raw = (form[key] ?? "").trim();
    if (raw === "") continue;
    const n = Number(raw);
    if (Number.isFinite(n) && n >= 0) out[key] = String(n);
  }
  return out;
}

/** What the macro editor should send as `values`, given the meal's current values and
 *  the edit form — or `undefined` when the four editable numbers weren't changed, so a
 *  rename alone doesn't turn derived numbers into a frozen override.
 *
 *  When they were changed, trackables the form doesn't show (fibre, sodium…) are
 *  carried over from the current values, because an override replaces the whole set
 *  and would otherwise drop them. An entirely blank form is `{}`: stop overriding. */
export function macroEditValues(
  current: Record<string, string>,
  form: Record<string, string>,
): Record<string, string> | undefined {
  const before = macrosFromForm(
    Object.fromEntries(EDITABLE_TRACKABLES.map((key) => [key, tidyNumber(current[key])])),
  );
  const after = macrosFromForm(form);
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  if ([...keys].every((key) => before[key] === after[key])) return undefined;
  if (Object.keys(after).length === 0) return {};
  const editable = EDITABLE_TRACKABLES as readonly string[];
  const others = Object.fromEntries(
    Object.entries(current).filter(([key]) => !editable.includes(key)),
  );
  return { ...others, ...after };
}

/** The single initial the phone ribbon shows. Two of them are "T" and two are "S",
 *  which is fine — position carries the rest, and the selected day is named in full
 *  above the list. */
export function dayLetter(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y!, m! - 1, d!).toLocaleDateString(undefined, { weekday: "narrow" }).charAt(0);
}

export interface RibbonDay {
  date: string;
  letter: string;
  /** How many of the day's four slots are filled — the dots under each pill. */
  filled: number;
  isToday: boolean;
  isSelected: boolean;
}

export function ribbonDays(
  days: { scheduled_for: string; meals: { meal_type: string }[] }[],
  selected: string,
  today: string,
): RibbonDay[] {
  return days.map((day) => ({
    date: day.scheduled_for,
    letter: dayLetter(day.scheduled_for),
    filled: day.meals.length,
    isToday: day.scheduled_for === today,
    isSelected: day.scheduled_for === selected,
  }));
}

/** Where the phone should land after the week changes underneath it: stay put if the
 *  day is still on screen, else today, else the start of the week. */
export function clampSelectedDay(selected: string, dates: string[], today: string): string {
  if (dates.length === 0 || dates.includes(selected)) return selected;
  if (dates.includes(today)) return today;
  return dates[0]!;
}
