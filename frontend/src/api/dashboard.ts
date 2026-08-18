import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

export function useNutritionCalendar(start: string, end: string) {
  return useQuery({
    queryKey: ["nutritionCalendar", start, end] as const,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/nutrition/calendar", {
        params: { query: { start, end } },
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
