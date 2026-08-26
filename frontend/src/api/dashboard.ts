import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

export function useNutritionCalendar(start: string, end: string) {
  return useQuery({
    queryKey: ["nutritionCalendar", start, end] as const,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/nutrition/calendar", {
        // tz_offset_minutes: see NutritionPage.tsx's tzOffsetMinutes doc comment — a
        // log made in the caller's local evening (west of UTC) can otherwise bucket
        // under the wrong calendar day.
        params: { query: { start, end, tz_offset_minutes: new Date().getTimezoneOffset() } },
      });
      if (error) throw new Error("Failed to load nutrition calendar");
      return data;
    },
  });
}

export function usePlannedWorkouts(start: string, end: string) {
  return useQuery({
    queryKey: ["plannedWorkouts", start, end] as const,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/planned-workouts", {
        params: { query: { start, end } },
      });
      if (error) throw new Error("Failed to load planned workouts");
      return data;
    },
  });
}

export function useWorkoutHistory(start: string, end: string) {
  return useQuery({
    queryKey: ["workoutHistory", start, end] as const,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workouts", {
        params: { query: { start, end } },
      });
      if (error) throw new Error("Failed to load workout history");
      return data;
    },
  });
}

// Self-service delete for a mistakenly-logged workout — history's own version of
// nutrition-day's meal-template delete control, so the user never has to ask for
// a one-off script against production again.
export function useDeleteWorkout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (workoutId: string) => {
      const { error } = await api.DELETE("/api/workouts/{workout_id}", {
        params: { path: { workout_id: workoutId } },
      });
      if (error) throw new Error("Failed to delete workout");
    },
    // Prefix match: invalidates every ["workoutHistory", start, end] query
    // regardless of the specific date range in its key.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workoutHistory"] }),
  });
}

export function useWorkoutStreak() {
  return useQuery({
    queryKey: ["workoutStreak"] as const,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workouts/streak");
      if (error) throw new Error("Failed to load workout streak");
      return data;
    },
  });
}
