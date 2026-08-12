import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";
import { useCompleteOnboarding, useProfile, useUpdateProfile } from "./profile";

vi.mock("./client", () => ({
  api: { GET: vi.fn(), PATCH: vi.fn(), POST: vi.fn() },
}));

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useProfile", () => {
  it("returns the caller's profile", async () => {
    vi.mocked(api.GET).mockResolvedValue({
      data: { weight_unit: "lbs", coach_notes: null, onboarding_completed_at: null },
      error: undefined,
    } as Awaited<ReturnType<typeof api.GET>>);

    const { result } = renderHook(() => useProfile(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.weight_unit).toBe("lbs");
    expect(api.GET).toHaveBeenCalledWith("/api/profile");
  });
});

describe("useUpdateProfile", () => {
  it("PATCHes the exact values passed in", async () => {
    vi.mocked(api.PATCH).mockResolvedValue({
      data: { weight_unit: "kg", coach_notes: "bad knee", onboarding_completed_at: null },
      error: undefined,
    } as Awaited<ReturnType<typeof api.PATCH>>);

    const { result } = renderHook(() => useUpdateProfile(), { wrapper });
    result.current.mutate({ weight_unit: "kg", coach_notes: "bad knee" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.PATCH).toHaveBeenCalledWith("/api/profile", {
      body: { weight_unit: "kg", coach_notes: "bad knee" },
    });
  });
});

describe("useCompleteOnboarding", () => {
  it("POSTs to the complete-onboarding endpoint", async () => {
    vi.mocked(api.POST).mockResolvedValue({
      data: { weight_unit: "lbs", coach_notes: null, onboarding_completed_at: "2026-08-11T00:00:00Z" },
      error: undefined,
    } as Awaited<ReturnType<typeof api.POST>>);

    const { result } = renderHook(() => useCompleteOnboarding(), { wrapper });
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.POST).toHaveBeenCalledWith("/api/profile/complete-onboarding");
  });
});
