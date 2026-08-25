import { useMutation } from "@tanstack/react-query";

import { api } from "./client";

/** Body weight, canonical pounds — always `weight_lbs` regardless of the user's
 *  display unit preference (matches app/services/workouts.py's MET-calorie estimate,
 *  which reads it back the same way). Logged via the same logs/log_values endpoint as
 *  food (trackable_types.category="body" keeps it out of the day's macro bars), so a
 *  log_nutrition call from Claude and this button land in the same place. No React
 *  Query invalidation needed here: log_nutrition publishes a "nutrition" SSE event,
 *  and NutritionPage/the dashboard already refetch off that. */
export function useLogWeight() {
  return useMutation({
    mutationFn: async (weightLbs: number) => {
      const { error } = await api.POST("/api/nutrition/logs", {
        body: {
          entries: [{ trackable_key: "weight_lbs", value: weightLbs }],
          name: "Weight",
          source: "manual",
        },
      });
      if (error) throw new Error("Failed to log weight");
    },
  });
}
