/**
 * Weight-prefill logic for the draft-set row, pulled out of main.ts so it's
 * testable without importing that module (which calls `app.connect()` at load
 * time — see main.ts's docstring). Pure functions, no DOM.
 */

export interface LastTimeSet {
  weight: number | null;
  reps: number | null;
}

/** The set about to be logged (`loggedSetCount` already logged this session)
 * lines up by position with last time's sets — a 2nd set today matches a 2nd
 * set last time, not whatever that session finished on — falling back to last
 * time's final set when that session had fewer sets than this one already
 * does. `undefined` (never logged, or last time had zero sets) leaves the
 * caller with nothing to prefill from. */
export function matchingLastTimeSet(
  lastTimeSets: LastTimeSet[],
  loggedSetCount: number,
): LastTimeSet | undefined {
  return lastTimeSets[loggedSetCount] ?? lastTimeSets[lastTimeSets.length - 1];
}

/** The draft weight input's initial value: a template's prescribed weight
 * wins outright, then the position-matched last-time set, then blank for a
 * brand-new exercise. Reps are deliberately never sourced from last time here
 * — weight only, per the prefill spec. */
export function prefillWeight(
  targetWeight: number | null | undefined,
  lastTimeSets: LastTimeSet[],
  loggedSetCount: number,
): string {
  if (targetWeight != null) return String(targetWeight);
  const lastSet = matchingLastTimeSet(lastTimeSets, loggedSetCount);
  return lastSet?.weight != null ? String(lastSet.weight) : "";
}
