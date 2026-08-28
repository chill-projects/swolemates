import { useProfile } from "../api/profile";

/** The browser's IANA zone, e.g. "America/Los_Angeles". "UTC" if `Intl` is unavailable. */
export function detectedTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/**
 * The timezone every date in the app is rendered and bucketed in: the user's stored
 * override (Settings → Timezone) if they set one, otherwise the browser's detected
 * zone. Mirrors the backend's resolution order — stored wins — so the SPA and the
 * server always agree on which calendar day an instant belongs to.
 *
 * `useProfile` is already fetched on app load and cached; while it's still pending
 * this returns the detected zone, which is the seed value anyway.
 */
export function useUserTimezone(): string {
  const { data } = useProfile();
  return data?.timezone ?? detectedTimezone();
}

/** `YYYY-MM-DD` for the calendar day `instant` falls on in `tz`. */
export function isoDateInTz(instant: Date | string | number, tz: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(instant));
}

/** Today's `YYYY-MM-DD` in `tz`. */
export function todayIsoInTz(tz: string): string {
  return isoDateInTz(Date.now(), tz);
}

/**
 * A local-midnight `Date` whose year/month/day equal the given `YYYY-MM-DD` — an
 * anchor for calendar-grid arithmetic and weekday formatting. Parses the parts
 * rather than `new Date(ymd)`, which would be read as UTC.
 */
export function dateFromIso(ymd: string): Date {
  const [y, m, d] = ymd.split("-").map(Number) as [number, number, number];
  return new Date(y, m - 1, d);
}

/** `YYYY-MM-DD` from a `Date`'s local year/month/day — the inverse of `dateFromIso`,
 *  for calendar-date anchors (never for an instant; use `isoDateInTz` there). */
export function isoFromDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Whole days from calendar date `fromIso` to `toIso` (both `YYYY-MM-DD`). */
export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((dateFromIso(toIso).getTime() - dateFromIso(fromIso).getTime()) / 86_400_000);
}

/** Format an instant for display in `tz`. Defaults to a medium date (no time). */
export function formatInstant(
  instant: Date | string | number,
  tz: string,
  opts: Intl.DateTimeFormatOptions = { dateStyle: "medium" },
): string {
  return new Intl.DateTimeFormat(undefined, { timeZone: tz, ...opts }).format(new Date(instant));
}
