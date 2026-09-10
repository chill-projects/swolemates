import { describe, expect, it, vi } from "vitest";

import { DAY_SCOPED_TOOLS, dayLabel, isoOf, shiftIso, todayIso, withViewedDay } from "./day";

describe("isoOf", () => {
  it("reads the local calendar date, not the UTC one", () => {
    // 2026-09-08 21:00 in a zone behind UTC is already the 9th in UTC. The card is
    // showing the user's day, so the string has to be the user's day.
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 8, 8, 21, 0, 0));
    expect(isoOf(new Date())).toBe("2026-09-08");
    expect(todayIso()).toBe("2026-09-08");
    vi.useRealTimers();
  });
});

describe("shiftIso", () => {
  it("steps a day back and forward", () => {
    expect(shiftIso("2026-09-08", -1)).toBe("2026-09-07");
    expect(shiftIso("2026-09-08", 1)).toBe("2026-09-09");
  });

  it("crosses a month and a year boundary", () => {
    expect(shiftIso("2026-09-01", -1)).toBe("2026-08-31");
    expect(shiftIso("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("survives a spring-forward date", () => {
    // 2026-03-08 is the US DST start. Anchoring at noon rather than midnight is what
    // keeps this from landing on an hour that doesn't exist locally and slipping a day.
    expect(shiftIso("2026-03-07", 1)).toBe("2026-03-08");
    expect(shiftIso("2026-03-08", -1)).toBe("2026-03-07");
  });
});

describe("dayLabel", () => {
  it("names today and yesterday rather than dating them", () => {
    expect(dayLabel("2026-09-10", "2026-09-10")).toBe("Today");
    expect(dayLabel("2026-09-09", "2026-09-10")).toBe("Yesterday");
  });

  it("dates anything further back", () => {
    expect(dayLabel("2026-09-07", "2026-09-10")).not.toBe("Today");
    expect(dayLabel("2026-09-07", "2026-09-10")).toMatch(/7/);
  });
});

describe("withViewedDay", () => {
  const viewed = "2026-09-07";

  it("tells a day-scoped tool which day the user is looking at", () => {
    expect(withViewedDay("log_nutrition", { name: "Toast" }, viewed)).toEqual({
      name: "Toast",
      date: viewed,
    });
  });

  it("sends nothing extra while the card is on today", () => {
    const args = { name: "Toast" };
    expect(withViewedDay("log_nutrition", args, null)).toBe(args);
  });

  it("leaves an explicit date alone", () => {
    const args = { date: "2026-09-01" };
    expect(withViewedDay("get_nutrition_day", args, viewed)).toBe(args);
  });

  it("never adds a date to update_nutrition_log", () => {
    // Its `date` moves the entry. Filling it in from the view would silently re-time
    // every meal-type edit made on a past day to noon.
    const args = { log_id: "abc", meal_type: "dinner" };
    expect(withViewedDay("update_nutrition_log", args, viewed)).toBe(args);
  });

  it("never adds a date to a tool that has no date param", () => {
    // search_food_facts takes no `date`; an unknown argument is a tool error, not a
    // no-op, so this one has to stay off the list.
    const args = { query: "oats" };
    expect(withViewedDay("search_food_facts", args, viewed)).toBe(args);
    expect(DAY_SCOPED_TOOLS.has("search_food_facts")).toBe(false);
  });
});
