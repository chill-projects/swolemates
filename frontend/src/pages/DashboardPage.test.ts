import { describe, expect, it } from "vitest";
import { heroTitle } from "./DashboardPage";
import type { components } from "../api/generated";

type NutritionCalendarDay = components["schemas"]["NutritionCalendarDayOut"];
type Streak = components["schemas"]["StreakOut"];

function day(consumed: string, target: string | null): NutritionCalendarDay {
  return {
    date: "2026-08-31",
    status: "hit",
    bars: [],
    hero: { trackable_key: "calories", label: "Calories", consumed, target, unit: "kcal" },
  };
}

function streak(target: number, this_week: number): Streak {
  return { target, this_week, weeks: 3 };
}

describe("heroTitle", () => {
  it("scopes each number to its own clock — kcal to today, workouts to the week", () => {
    expect(heroTitle(day("585", "1550"), streak(5, 1))).toBe(
      "965 kcal left today and 4 workouts left this week.",
    );
  });

  it("shows only the calorie half when the week's workouts are done", () => {
    expect(heroTitle(day("585", "1550"), streak(5, 5))).toBe("965 kcal left today.");
  });

  it("shows only the workout half once today's calories are met", () => {
    expect(heroTitle(day("1550", "1550"), streak(5, 1))).toBe("4 workouts left this week.");
  });

  it("falls back to a combined on-target message when both are done", () => {
    expect(heroTitle(day("1550", "1550"), streak(5, 5))).toBe(
      "You’re on target for today and the week.",
    );
  });

  it("treats a missing calorie target the same as calories being met", () => {
    expect(heroTitle(day("400", null), streak(5, 5))).toBe(
      "You’re on target for today and the week.",
    );
  });

  it("handles missing data (no day, no streak) as the on-target fallback", () => {
    expect(heroTitle(undefined, undefined)).toBe("You’re on target for today and the week.");
  });
});
