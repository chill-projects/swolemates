import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./generated";

type ProfileUpdateBody = components["schemas"]["ProfileUpdate"];
export type CalculateTargetsResponse = components["schemas"]["CalculateTargetsResponse"];

const PROFILE_KEY = ["profile"] as const;

export function useProfile() {
  return useQuery({
    queryKey: PROFILE_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/profile");
      if (error) throw new Error("Failed to load profile");
      return data;
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ProfileUpdateBody) => {
      const { data, error } = await api.PATCH("/api/profile", { body });
      if (error) throw new Error("Failed to update profile");
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PROFILE_KEY }),
  });
}

export function useCalculateTargets() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/tdee/calculate-targets");
      if (error) {
        // The 400 case names exactly what's missing (e.g. "sex, age, ... a logged
        // weight") — worth surfacing as-is rather than a generic failure message.
        const detail = (error as { detail?: unknown }).detail;
        throw new Error(typeof detail === "string" ? detail : "Failed to calculate targets");
      }
      return data;
    },
    // Targets land as goals — nothing in this app caches those yet, but keep the
    // profile query fresh since this reads it.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PROFILE_KEY }),
  });
}

export function useCompleteOnboarding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/profile/complete-onboarding");
      if (error) throw new Error("Failed to complete onboarding");
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PROFILE_KEY }),
  });
}
