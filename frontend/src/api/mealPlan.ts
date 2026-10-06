import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { components } from "./generated";
import { api } from "./client";

export type PlannedDay = components["schemas"]["PlannedDayOut"];
export type PlannedMeal = components["schemas"]["PlannedMealOut"];
export type KitchenItem = components["schemas"]["KitchenItemOut"];

const KITCHEN_KEY = ["kitchen"] as const;
const planKey = (start: string, end: string) => ["mealPlan", start, end] as const;

export function useMealPlan(start: string, end: string) {
  return useQuery({
    queryKey: planKey(start, end),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/meal-plan", {
        params: { query: { start, end } },
      });
      if (error || !data) throw new Error("Failed to load your meal plan");
      return data;
    },
  });
}

export function useKitchen() {
  return useQuery({
    queryKey: KITCHEN_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/kitchen");
      if (error || !data) throw new Error("Failed to load what needs eating");
      return data;
    },
  });
}

/** Logging a planned meal writes a real nutrition entry, so every mutation also
 *  invalidates the React Query reads built on logged food: the dashboard's
 *  `nutritionCalendar` and the Plan tab's `weeklyCheckin` (days logged). The Nutrition
 *  tab itself isn't a query — it refetches off the "nutrition" SSE event the log
 *  publishes. */
function useInvalidatePlan() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["mealPlan"] });
    void queryClient.invalidateQueries({ queryKey: KITCHEN_KEY });
    void queryClient.invalidateQueries({ queryKey: ["nutritionCalendar"] });
    void queryClient.invalidateQueries({ queryKey: ["weeklyCheckin"] });
  };
}

export type PlanMealBody = components["schemas"]["PlanMealRequest"];

export function usePlanMeal() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: async (body: PlanMealBody) => {
      const { data, error } = await api.POST("/api/meal-plan", { body });
      if (error || !data) throw new Error("Couldn't put that on the plan");
      return data;
    },
    onSuccess: invalidate,
  });
}

export type UpdatePlannedMealBody = components["schemas"]["UpdatePlannedMealRequest"];

export function useUpdatePlannedMeal() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: UpdatePlannedMealBody }) => {
      const { data, error } = await api.PATCH("/api/meal-plan/{planned_meal_id}", {
        params: { path: { planned_meal_id: id } },
        body,
      });
      if (error || !data) throw new Error("Couldn't save that change");
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useClearPlannedMeal() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE("/api/meal-plan/{planned_meal_id}", {
        params: { path: { planned_meal_id: id } },
      });
      if (error) throw new Error("Couldn't clear that slot");
    },
    onSuccess: invalidate,
  });
}

export function useLogPlannedMeal() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await api.POST("/api/meal-plan/{planned_meal_id}/log", {
        params: { path: { planned_meal_id: id } },
      });
      if (error || !data) throw new Error("Couldn't log that meal");
      return data;
    },
    onSuccess: invalidate,
  });
}

export type AddKitchenItemBody = components["schemas"]["AddKitchenItemRequest"];

export function useAddKitchenItem() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: async (body: AddKitchenItemBody) => {
      const { data, error } = await api.POST("/api/kitchen", { body });
      if (error || !data) throw new Error("Couldn't add that");
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useRemoveKitchenItem() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE("/api/kitchen/{item_id}", {
        params: { path: { item_id: id } },
      });
      if (error) throw new Error("Couldn't remove that");
    },
    onSuccess: invalidate,
  });
}
