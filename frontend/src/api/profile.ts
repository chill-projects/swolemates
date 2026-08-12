import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

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
    mutationFn: async (body: { weight_unit?: "lbs" | "kg"; coach_notes?: string }) => {
      const { data, error } = await api.PATCH("/api/profile", { body });
      if (error) throw new Error("Failed to update profile");
      return data;
    },
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
