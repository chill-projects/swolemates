/**
 * Draft state for the template editor, pulled out of main.ts so it's testable
 * without importing that module (which calls `app.connect()` at load time — see
 * main.ts's docstring). Pure functions, no DOM.
 *
 * The editor used to write each field straight to the server on blur, which made
 * every field its own save, every save its own full re-render, and — because the
 * SPA host's tool handler refetches the template list — every save its own iframe
 * teardown. Edits collect here instead until the user hits Save, and the whole
 * batch goes out as one run of `update_exercise` calls.
 */

export type NumericField = "sets" | "reps" | "seconds" | "weight";
export type DraftField = NumericField | "notes";

/** What the server currently holds for one template exercise. */
export interface SavedTargets {
  sets: number;
  reps: number | null;
  seconds: number | null;
  weight: number | null;
  notes: string | null;
}

export type Draft = Partial<{
  sets: number;
  reps: number;
  seconds: number;
  weight: number;
  notes: string;
}>;

/** Keyed by template_exercise_id. Only fields that actually differ from the
 *  server live here, so `size === 0` is exactly "nothing to save". */
export type Drafts = ReadonlyMap<string, Draft>;

export const NO_DRAFTS: Drafts = new Map();

/** Parse a number input's raw value. Blank is `null` — "the user didn't give one",
 *  which is a different thing from 0 and is why this doesn't just return NaN. */
export function parseNumberField(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

function matchesSaved(field: DraftField, value: number | string, saved: SavedTargets): boolean {
  if (field === "notes") return String(value) === (saved.notes ?? "");
  return value === saved[field];
}

/**
 * Record one field edit — or forget it, if the value has come back to what the
 * server already has. Typing "12" into a reps box and then fixing it back to "10"
 * leaves the template clean, so Save doesn't light up for a no-op.
 */
export function stageEdit(
  drafts: Drafts,
  id: string,
  field: DraftField,
  value: number | string,
  saved: SavedTargets,
): Drafts {
  const next = new Map(drafts);
  const entry: Draft = { ...next.get(id) };
  if (matchesSaved(field, value, saved)) delete entry[field];
  else Object.assign(entry, { [field]: value });
  if (Object.keys(entry).length === 0) next.delete(id);
  else next.set(id, entry);
  return next;
}

/** Drop a staged edit without touching the rest. Used for a blanked weight box:
 *  the service reads a missing weight as "leave it alone", so there's no way to
 *  express "clear it" and the honest thing is to treat blank as no edit. */
export function clearEdit(drafts: Drafts, id: string, field: DraftField): Drafts {
  const existing = drafts.get(id);
  if (!existing || !(field in existing)) return drafts;
  const next = new Map(drafts);
  const entry: Draft = { ...existing };
  delete entry[field];
  if (Object.keys(entry).length === 0) next.delete(id);
  else next.set(id, entry);
  return next;
}

/** What an input should show: the pending edit if there is one, else the server's
 *  value. Written as `field in entry` rather than a truthiness check so a staged 0
 *  still wins over the saved value. */
export function effectiveValue(
  drafts: Drafts,
  id: string,
  field: DraftField,
  saved: SavedTargets,
): number | string | null {
  const entry = drafts.get(id);
  if (entry && field in entry) return entry[field] ?? null;
  return saved[field];
}

/** Why this value can't be saved, or null if it can. Blank never reaches here —
 *  see `parseNumberField` and the weight carve-out in `clearEdit`. */
export function fieldIssue(field: DraftField, value: number | string): string | null {
  if (field === "notes") return null;
  if (typeof value !== "number" || !Number.isFinite(value)) return "needs a number";
  // Half-pound plates are a real thing; half a rep is not.
  if (field === "weight") return value < 0 ? "can't be negative" : null;
  if (!Number.isInteger(value)) return "needs a whole number";
  return value < 1 ? "needs to be at least 1" : null;
}

export interface DraftIssue {
  id: string;
  field: DraftField;
  message: string;
}

export function draftIssues(drafts: Drafts): DraftIssue[] {
  const issues: DraftIssue[] = [];
  for (const [id, entry] of drafts) {
    for (const [field, value] of Object.entries(entry) as [DraftField, number | string][]) {
      const message = fieldIssue(field, value);
      if (message) issues.push({ id, field, message });
    }
  }
  return issues;
}

/** One `update_exercise` call's arguments per edited exercise. Batching by
 *  exercise rather than by field is what turns "I changed five things" into at
 *  most a handful of round trips instead of five. */
export function pendingEdits(drafts: Drafts): { template_exercise_id: string; fields: Draft }[] {
  return [...drafts].map(([id, fields]) => ({ template_exercise_id: id, fields }));
}

/** How many individual fields are waiting, for the "3 unsaved changes" label.
 *  Fields, not exercises — that's the unit the user just typed in. */
export function dirtyFieldCount(drafts: Drafts, nameChanged: boolean): number {
  let count = nameChanged ? 1 : 0;
  for (const entry of drafts.values()) count += Object.keys(entry).length;
  return count;
}

export function describeDirty(count: number): string {
  if (count === 0) return "";
  return `${count} unsaved change${count === 1 ? "" : "s"}`;
}
