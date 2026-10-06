import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

const PATTERN_KEY = ["weeklyPattern"] as const;
const TEMPLATES_KEY = ["templates"] as const;
const CHECKIN_KEY = ["weeklyCheckin"] as const;

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

/** The weekly check-in. No `as_of`: the server resolves "today" in the caller's zone
 *  from the `X-Timezone` header, same as every other day-scoped read. */
export function useWeeklyCheckin() {
  return useQuery({
    queryKey: CHECKIN_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/weekly-checkin");
      if (error) throw new Error("Failed to load your check-in");
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
      void queryClient.invalidateQueries({ queryKey: CHECKIN_KEY });
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

/** Archiving a template changes more than the library: a patterned day pointing at it
 *  becomes a silent rest day, which the check-in surfaces as a decision and the next
 *  seven days stop showing. So every view derived from the pattern is invalidated, not
 *  just the template list. */
export function useArchiveTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (templateId: string) => {
      const { error } = await api.POST("/api/templates/{template_id}/archive", {
        params: { path: { template_id: templateId } },
      });
      if (error) throw new Error("archive failed");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: TEMPLATES_KEY });
      void queryClient.invalidateQueries({ queryKey: PATTERN_KEY });
      void queryClient.invalidateQueries({ queryKey: CHECKIN_KEY });
      void queryClient.invalidateQueries({ queryKey: ["plannedWorkouts"] });
    },
  });
}
