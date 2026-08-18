import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

const PARTNER_KEY = ["partner"] as const;

function errorDetail(error: unknown, fallback: string): string {
  const detail = (error as { detail?: unknown } | null)?.detail;
  return typeof detail === "string" ? detail : fallback;
}

export function usePartnerSummary() {
  return useQuery({
    queryKey: PARTNER_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/partner");
      if (error) throw new Error("Failed to load partner summary");
      return data;
    },
  });
}

export function useGenerateInvite() {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/partner/invite");
      if (error) throw new Error(errorDetail(error, "Failed to generate an invite"));
      return data;
    },
  });
}

export function useInvitePreview(code: string) {
  return useQuery({
    queryKey: ["partnerInvitePreview", code] as const,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/partner/invite/{code}", {
        params: { path: { code } },
      });
      if (error) throw new Error("Failed to load this invite");
      return data;
    },
  });
}

export function useRedeemInvite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (code: string) => {
      const { data, error } = await api.POST("/api/partner/redeem", { body: { code } });
      if (error) throw new Error(errorDetail(error, "Failed to redeem this invite"));
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PARTNER_KEY }),
  });
}
