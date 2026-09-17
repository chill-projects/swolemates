import { describe, expect, it } from "vitest";

import {
  type Drafts,
  type SavedTargets,
  NO_DRAFTS,
  clearEdit,
  describeDirty,
  dirtyFieldCount,
  draftIssues,
  effectiveValue,
  fieldIssue,
  parseNumberField,
  pendingEdits,
  stageEdit,
} from "./drafts";

const SAVED: SavedTargets = { sets: 3, reps: 10, seconds: null, weight: 135, notes: "pause at chest" };
const HOLD: SavedTargets = { sets: 3, reps: null, seconds: 45, weight: null, notes: null };

describe("parseNumberField", () => {
  it("reads a number", () => {
    expect(parseNumberField("12")).toBe(12);
    expect(parseNumberField(" 2.5 ")).toBe(2.5);
  });

  it("treats blank as absent rather than zero", () => {
    expect(parseNumberField("")).toBeNull();
    expect(parseNumberField("   ")).toBeNull();
  });

  it("refuses junk", () => {
    expect(parseNumberField("abc")).toBeNull();
  });
});

describe("stageEdit", () => {
  it("records a changed field", () => {
    const drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    expect(drafts.get("a")).toEqual({ reps: 12 });
  });

  it("collects several fields on one exercise", () => {
    let drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    drafts = stageEdit(drafts, "a", "weight", 145, SAVED);
    expect(drafts.get("a")).toEqual({ reps: 12, weight: 145 });
  });

  it("keeps exercises independent", () => {
    let drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    drafts = stageEdit(drafts, "b", "sets", 4, SAVED);
    expect([...drafts.keys()]).toEqual(["a", "b"]);
  });

  // Typing 12 and then fixing it back to 10 should leave the template clean —
  // otherwise Save lights up for a no-op and the user can't tell what's pending.
  it("forgets an edit that lands back on the saved value", () => {
    let drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    drafts = stageEdit(drafts, "a", "reps", 10, SAVED);
    expect(drafts.has("a")).toBe(false);
  });

  it("drops the exercise only once its last field is reverted", () => {
    let drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    drafts = stageEdit(drafts, "a", "sets", 4, SAVED);
    drafts = stageEdit(drafts, "a", "reps", 10, SAVED);
    expect(drafts.get("a")).toEqual({ sets: 4 });
  });

  it("compares notes against empty string when the server has none", () => {
    let drafts = stageEdit(NO_DRAFTS, "a", "notes", "tempo", HOLD);
    expect(drafts.get("a")).toEqual({ notes: "tempo" });
    drafts = stageEdit(drafts, "a", "notes", "", HOLD);
    expect(drafts.has("a")).toBe(false);
  });

  it("stages an emptied note, which does clear on the server", () => {
    const drafts = stageEdit(NO_DRAFTS, "a", "notes", "", SAVED);
    expect(drafts.get("a")).toEqual({ notes: "" });
  });

  it("does not mutate the map it was given", () => {
    const before: Drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    stageEdit(before, "a", "sets", 5, SAVED);
    expect(before.get("a")).toEqual({ reps: 12 });
  });
});

describe("clearEdit", () => {
  it("removes one field and leaves the rest", () => {
    let drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    drafts = stageEdit(drafts, "a", "weight", 145, SAVED);
    drafts = clearEdit(drafts, "a", "weight");
    expect(drafts.get("a")).toEqual({ reps: 12 });
  });

  it("drops the exercise when nothing is left", () => {
    let drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    drafts = clearEdit(drafts, "a", "reps");
    expect(drafts.size).toBe(0);
  });

  it("is a no-op for a field that was never staged", () => {
    const drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    expect(clearEdit(drafts, "a", "sets")).toBe(drafts);
    expect(clearEdit(drafts, "zzz", "sets")).toBe(drafts);
  });
});

describe("effectiveValue", () => {
  it("prefers the pending edit", () => {
    const drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    expect(effectiveValue(drafts, "a", "reps", SAVED)).toBe(12);
  });

  it("falls back to the saved value", () => {
    expect(effectiveValue(NO_DRAFTS, "a", "weight", SAVED)).toBe(135);
    expect(effectiveValue(NO_DRAFTS, "a", "weight", HOLD)).toBeNull();
  });

  // A staged 0 is falsy; the lookup has to ask whether the key is present, not
  // whether the value is truthy, or a zeroed box would silently show the old number.
  it("honours a staged zero", () => {
    const drafts = stageEdit(NO_DRAFTS, "a", "weight", 0, SAVED);
    expect(effectiveValue(drafts, "a", "weight", SAVED)).toBe(0);
  });
});

describe("fieldIssue", () => {
  it("accepts sane targets", () => {
    expect(fieldIssue("sets", 3)).toBeNull();
    expect(fieldIssue("reps", 10)).toBeNull();
    expect(fieldIssue("seconds", 45)).toBeNull();
  });

  it("rejects counts below one", () => {
    expect(fieldIssue("sets", 0)).toMatch(/at least 1/);
    expect(fieldIssue("reps", -2)).toMatch(/at least 1/);
  });

  it("rejects fractional counts", () => {
    expect(fieldIssue("reps", 1.5)).toMatch(/whole number/);
  });

  // Half-pound plates are a real thing, and an unloaded bar is a real weight.
  it("allows fractional and zero weight but not negative", () => {
    expect(fieldIssue("weight", 2.5)).toBeNull();
    expect(fieldIssue("weight", 0)).toBeNull();
    expect(fieldIssue("weight", -5)).toMatch(/negative/);
  });

  it("accepts any note", () => {
    expect(fieldIssue("notes", "")).toBeNull();
    expect(fieldIssue("notes", "3s eccentric")).toBeNull();
  });
});

describe("draftIssues", () => {
  it("is empty for a valid batch", () => {
    const drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    expect(draftIssues(drafts)).toEqual([]);
  });

  it("names the exercise and field that block the save", () => {
    let drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    drafts = stageEdit(drafts, "b", "sets", 0, SAVED);
    expect(draftIssues(drafts)).toEqual([
      { id: "b", field: "sets", message: expect.stringMatching(/at least 1/) as unknown as string },
    ]);
  });
});

describe("pendingEdits", () => {
  it("produces one update per edited exercise, not per field", () => {
    let drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    drafts = stageEdit(drafts, "a", "weight", 145, SAVED);
    drafts = stageEdit(drafts, "b", "sets", 4, SAVED);
    expect(pendingEdits(drafts)).toEqual([
      { template_exercise_id: "a", fields: { reps: 12, weight: 145 } },
      { template_exercise_id: "b", fields: { sets: 4 } },
    ]);
  });

  it("is empty when nothing is staged", () => {
    expect(pendingEdits(NO_DRAFTS)).toEqual([]);
  });
});

describe("dirtyFieldCount", () => {
  it("counts fields across exercises", () => {
    let drafts = stageEdit(NO_DRAFTS, "a", "reps", 12, SAVED);
    drafts = stageEdit(drafts, "a", "weight", 145, SAVED);
    drafts = stageEdit(drafts, "b", "notes", "slow", SAVED);
    expect(dirtyFieldCount(drafts, false)).toBe(3);
  });

  it("counts a pending rename", () => {
    expect(dirtyFieldCount(NO_DRAFTS, true)).toBe(1);
    expect(dirtyFieldCount(NO_DRAFTS, false)).toBe(0);
  });
});

describe("describeDirty", () => {
  it("reads naturally at each count", () => {
    expect(describeDirty(0)).toBe("");
    expect(describeDirty(1)).toBe("1 unsaved change");
    expect(describeDirty(4)).toBe("4 unsaved changes");
  });
});
