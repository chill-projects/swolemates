import { describe, expect, it } from "vitest";

import {
  addDays,
  clampSelectedDay,
  dayLabel,
  dayLetter,
  dayMacros,
  isoDate,
  macroEditValues,
  macroLabel,
  macrosFromForm,
  ribbonDays,
  sortBySlot,
  tidyNumber,
  weekDates,
  weekStart,
} from "./mealPlan";

const meal = (
  meal_type: string,
  values: Record<string, string>,
  estimated = true,
) => ({ meal_type, values, estimated });

describe("weekStart", () => {
  it("is Monday-first, matching the workout pattern's numbering", () => {
    // 2026-10-01 is a Thursday.
    expect(isoDate(weekStart(new Date(2026, 9, 1)))).toBe("2026-09-28");
  });

  it("leaves a Monday where it is", () => {
    expect(isoDate(weekStart(new Date(2026, 8, 28)))).toBe("2026-09-28");
  });

  it("treats Sunday as the end of its week, not the start", () => {
    expect(isoDate(weekStart(new Date(2026, 9, 4)))).toBe("2026-09-28");
  });
});

describe("weekDates", () => {
  it("gives seven consecutive days", () => {
    expect(weekDates(new Date(2026, 9, 1))).toEqual([
      "2026-09-28",
      "2026-09-29",
      "2026-09-30",
      "2026-10-01",
      "2026-10-02",
      "2026-10-03",
      "2026-10-04",
    ]);
  });

  it("crosses a month boundary without drifting", () => {
    expect(weekDates(new Date(2026, 11, 31))).toEqual([
      "2026-12-28",
      "2026-12-29",
      "2026-12-30",
      "2026-12-31",
      "2027-01-01",
      "2027-01-02",
      "2027-01-03",
    ]);
  });
});

describe("isoDate", () => {
  // toISOString() would shift the date for anyone west of UTC; this is why the
  // helper builds the string by hand.
  it("uses the local date, not UTC", () => {
    expect(isoDate(new Date(2026, 0, 1))).toBe("2026-01-01");
    expect(isoDate(new Date(2026, 11, 31))).toBe("2026-12-31");
  });

  it("zero-pads", () => {
    expect(isoDate(new Date(2026, 2, 5))).toBe("2026-03-05");
  });
});

describe("addDays", () => {
  it("rolls over a month end", () => {
    expect(isoDate(addDays(new Date(2026, 8, 30), 1))).toBe("2026-10-01");
  });

  it("goes backwards too", () => {
    expect(isoDate(addDays(new Date(2026, 9, 1), -1))).toBe("2026-09-30");
  });
});

describe("dayLabel", () => {
  it("names the weekday of the date given, parsed locally", () => {
    expect(dayLabel("2026-09-28")).toMatch(/Mon/);
    expect(dayLabel("2026-10-04")).toMatch(/Sun/);
  });
});

describe("sortBySlot", () => {
  it("puts the day in eating order regardless of insertion order", () => {
    const sorted = sortBySlot([
      meal("snack", {}),
      meal("breakfast", {}),
      meal("dinner", {}),
      meal("lunch", {}),
    ]);
    expect(sorted.map((m) => m.meal_type)).toEqual([
      "breakfast",
      "lunch",
      "dinner",
      "snack",
    ]);
  });

  it("does not mutate its input", () => {
    const input = [meal("snack", {}), meal("breakfast", {})];
    sortBySlot(input);
    expect(input.map((m) => m.meal_type)).toEqual(["snack", "breakfast"]);
  });
});

describe("dayMacros", () => {
  it("adds up what it knows", () => {
    expect(
      dayMacros([
        meal("breakfast", { calories: "360", protein_g: "18" }),
        meal("lunch", { calories: "620", protein_g: "52" }),
      ]),
    ).toEqual({ calories: 980, protein: 70, unestimated: 0 });
  });

  // The whole point: a meal nobody has numbers for must not read as zero.
  it("counts an unestimated meal instead of adding zero for it", () => {
    expect(
      dayMacros([
        meal("breakfast", { calories: "360", protein_g: "18" }),
        meal("dinner", {}, false),
      ]),
    ).toEqual({ calories: 360, protein: 18, unestimated: 1 });
  });

  it("is all zeroes for an empty day", () => {
    expect(dayMacros([])).toEqual({ calories: 0, protein: 0, unestimated: 0 });
  });

  it("tolerates a meal missing one trackable", () => {
    expect(dayMacros([meal("snack", { calories: "120" })])).toEqual({
      calories: 120,
      protein: 0,
      unestimated: 0,
    });
  });
});

describe("macroLabel", () => {
  it("reads as numbers when they're known", () => {
    expect(macroLabel(meal("lunch", { calories: "620.0", protein_g: "52" }))).toBe(
      "620 kcal · 52 g",
    );
  });

  it("says so when they aren't", () => {
    expect(macroLabel(meal("dinner", {}, false))).toBe("not estimated");
  });
});

describe("tidyNumber", () => {
  it("drops the trailing zeros a portion multiply leaves", () => {
    expect(tidyNumber("390.0")).toBe("390");
    expect(tidyNumber("24.00")).toBe("24");
  });

  it("keeps a real fraction", () => {
    expect(tidyNumber("2.5")).toBe("2.5");
  });

  it("is blank for nothing", () => {
    expect(tidyNumber(null)).toBe("");
    expect(tidyNumber("")).toBe("");
    expect(tidyNumber("abc")).toBe("");
  });
});

describe("macrosFromForm", () => {
  it("keeps what was filled in", () => {
    expect(macrosFromForm({ calories: "650", protein_g: "60" })).toEqual({
      calories: "650",
      protein_g: "60",
    });
  });

  it("drops blanks rather than sending zeros", () => {
    expect(macrosFromForm({ calories: "650", protein_g: "  " })).toEqual({
      calories: "650",
    });
  });

  // An entirely blank form is how the UI says "stop overriding these".
  it("is empty when nothing was filled in, which clears the override", () => {
    expect(macrosFromForm({ calories: "", protein_g: "" })).toEqual({});
  });

  it("refuses junk and negatives", () => {
    expect(macrosFromForm({ calories: "abc", protein_g: "-5" })).toEqual({});
  });

  it("ignores keys the planner doesn't edit", () => {
    expect(macrosFromForm({ calories: "100", fiber_g: "9" })).toEqual({ calories: "100" });
  });
});

describe("dayLetter", () => {
  it("is the single initial the ribbon shows", () => {
    expect(dayLetter("2026-09-28")).toBe("M");
    expect(dayLetter("2026-09-30")).toBe("W");
    expect(dayLetter("2026-10-04")).toBe("S");
  });
});

describe("ribbonDays", () => {
  const week = [
    { scheduled_for: "2026-09-28", meals: [{ meal_type: "breakfast" }, { meal_type: "lunch" }] },
    { scheduled_for: "2026-09-29", meals: [] },
    { scheduled_for: "2026-09-30", meals: [{ meal_type: "dinner" }] },
  ];

  it("counts how full each day is, which is what the dots show", () => {
    const pills = ribbonDays(week, "2026-09-29", "2026-09-28");
    expect(pills.map((p) => p.filled)).toEqual([2, 0, 1]);
  });

  it("marks the selected day and today independently", () => {
    const pills = ribbonDays(week, "2026-09-29", "2026-09-28");
    expect(pills.map((p) => p.isSelected)).toEqual([false, true, false]);
    expect(pills.map((p) => p.isToday)).toEqual([true, false, false]);
  });

  it("can have today selected as well", () => {
    const pills = ribbonDays(week, "2026-09-28", "2026-09-28");
    expect(pills[0]).toMatchObject({ isSelected: true, isToday: true });
  });

  it("carries the letter and the date through", () => {
    expect(ribbonDays(week, "2026-09-28", "2026-09-28")[2]).toMatchObject({
      date: "2026-09-30",
      letter: "W",
    });
  });
});

describe("clampSelectedDay", () => {
  const dates = ["2026-09-28", "2026-09-29", "2026-09-30"];

  it("keeps a selection that is still in the week", () => {
    expect(clampSelectedDay("2026-09-29", dates, "2026-09-28")).toBe("2026-09-29");
  });

  // Paging the week must land somewhere sensible rather than on a blank day.
  it("falls to today when the selection has scrolled out of the week", () => {
    expect(clampSelectedDay("2026-10-05", dates, "2026-09-30")).toBe("2026-09-30");
  });

  it("falls to the first day when today is not in the week either", () => {
    expect(clampSelectedDay("2026-10-05", dates, "2026-11-01")).toBe("2026-09-28");
  });

  it("copes with an empty week", () => {
    expect(clampSelectedDay("2026-10-05", [], "2026-11-01")).toBe("2026-10-05");
  });
});

describe("macroEditValues", () => {
  const current = { calories: "780.00", protein_g: "48", fiber_g: "6" };
  const formOf = (v: Record<string, string>) => ({
    calories: tidyNumber(v.calories),
    protein_g: tidyNumber(v.protein_g),
    carbs_g: tidyNumber(v.carbs_g),
    fat_g: tidyNumber(v.fat_g),
  });

  it("sends nothing when the numbers weren't touched, so a rename stays derived", () => {
    expect(macroEditValues(current, formOf(current))).toBeUndefined();
  });

  it("keeps trackables the form doesn't show when the numbers change", () => {
    expect(macroEditValues(current, { ...formOf(current), calories: "650" })).toEqual({
      calories: "650",
      protein_g: "48",
      fiber_g: "6",
    });
  });

  it("sends {} when every field is blanked, which clears the override", () => {
    expect(macroEditValues(current, { calories: "", protein_g: "" })).toEqual({});
  });

  it("sends nothing for an unestimated meal left blank", () => {
    expect(macroEditValues({}, { calories: "" })).toBeUndefined();
  });
});
