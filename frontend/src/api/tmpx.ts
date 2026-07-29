import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

const TMPX_KEY = ["tmpx"] as const;

export function useTmpxItems() {
  return useQuery({
    queryKey: TMPX_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/tmpx");
      if (error) throw new Error("Failed to load items");
      return data;
    },
  });
}

export function useAddTmpxItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { name: string; value: number }) => {
      const { data, error } = await api.POST("/api/tmpx", { body });
      if (error) throw new Error("Failed to add item");
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TMPX_KEY }),
  });
}

export function useDeleteTmpxItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE("/api/tmpx/{item_id}", {
        params: { path: { item_id: id } },
      });
      if (error) throw new Error("Failed to delete item");
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TMPX_KEY }),
  });
}

export function useWhoami() {
  return useQuery({
    queryKey: ["whoami"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/whoami");
      if (error) throw new Error("Not authenticated");
      return data;
    },
    retry: false,
  });
}
