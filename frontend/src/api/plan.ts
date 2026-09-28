import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

const PATTERN_KEY = ["weeklyPattern"] as const;
const TEMPLATES_KEY = ["templates"] as const;

export function useWeeklyPattern() {
  return useQuery({
    queryKey: PATTERN_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/weekly-pattern");
      if (error) throw new Error("Failed to load your weekly pattern");
      return data;
    },
  });
}

export type PatternDayInput = { day_of_week: number; template_id: string | null };

/** The pattern is written whole, not per day — the PUT replaces all seven, which is
 *  also how the MCP `set_weekly_pattern` tool behaves. Planned workouts are
 *  regenerated from it server-side, so both queries are invalidated on success. */
export function useSetWeeklyPattern() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (days: PatternDayInput[]) => {
      const { data, error } = await api.PUT("/api/weekly-pattern", { body: { days } });
      if (error) throw new Error("Failed to save your weekly pattern");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PATTERN_KEY });
      void queryClient.invalidateQueries({ queryKey: ["plannedWorkouts"] });
    },
  });
}

export function useTemplates() {
  return useQuery({
    queryKey: TEMPLATES_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/templates");
      if (error) throw new Error("Failed to load your templates");
      return data;
    },
  });
}

/** Planned sessions for a date range. The meal plan's phone view reads this so a day
 *  shows its training and its eating together — on a narrow screen they'd otherwise
 *  sit in two separate scrolling cards, which is the split the Plan tab exists to
 *  avoid. */
export function usePlannedWorkouts(start: string, end: string) {
  return useQuery({
    queryKey: ["plannedWorkouts", start, end],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/planned-workouts", {
        params: { query: { start, end } },
      });
      if (error || !data) throw new Error("Failed to load your planned sessions");
      return data;
    },
  });
}
