import { describe, expect, it } from "vitest";
import { matchingLastTimeSet, prefillWeight, type LastTimeSet } from "./prefill";

const threeSets: LastTimeSet[] = [
  { weight: 95, reps: 8 },
  { weight: 100, reps: 6 },
  { weight: 105, reps: 5 },
];

describe("matchingLastTimeSet", () => {
  it("matches by position: the Nth set today lines up with the Nth set last time", () => {
    expect(matchingLastTimeSet(threeSets, 0)).toEqual({ weight: 95, reps: 8 });
    expect(matchingLastTimeSet(threeSets, 1)).toEqual({ weight: 100, reps: 6 });
    expect(matchingLastTimeSet(threeSets, 2)).toEqual({ weight: 105, reps: 5 });
  });

  it("falls back to last time's final set once today's count exceeds it", () => {
    expect(matchingLastTimeSet(threeSets, 3)).toEqual({ weight: 105, reps: 5 });
    expect(matchingLastTimeSet(threeSets, 10)).toEqual({ weight: 105, reps: 5 });
  });

  it("returns undefined when there's no last-time history at all", () => {
    expect(matchingLastTimeSet([], 0)).toBeUndefined();
  });
});

describe("prefillWeight", () => {
  it("stays blank for a never-logged exercise", () => {
    expect(prefillWeight(undefined, [], 0)).toBe("");
    expect(prefillWeight(null, [], 0)).toBe("");
  });

  it("prefills from the position-matched last-time set", () => {
    expect(prefillWeight(undefined, threeSets, 1)).toBe("100");
  });

  it("falls back to the last-time set's weight when the count doesn't match", () => {
    expect(prefillWeight(undefined, threeSets, 5)).toBe("105");
  });

  it("prefers a template's target weight over history", () => {
    expect(prefillWeight(135, threeSets, 1)).toBe("135");
  });

  it("treats a target weight of 0 as a real prescription, not 'unset'", () => {
    // 0 is a valid bodyweight-exercise weight — must not fall through to history.
    expect(prefillWeight(0, threeSets, 1)).toBe("0");
  });

  it("falls through to '' when a logged set exists but its weight is null", () => {
    expect(prefillWeight(undefined, [{ weight: null, reps: 8 }], 0)).toBe("");
  });
});
