import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCompleteOnboarding, useUpdateProfile } from "../api/profile";
import { ProfileForm } from "./ProfileForm";

vi.mock("../api/profile", () => ({
  useUpdateProfile: vi.fn(),
  useCompleteOnboarding: vi.fn(),
}));

const mutateUpdate = vi.fn();
const mutateComplete = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useUpdateProfile).mockReturnValue({
    mutate: mutateUpdate,
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateProfile>);
  vi.mocked(useCompleteOnboarding).mockReturnValue({
    mutate: mutateComplete,
    isPending: false,
  } as unknown as ReturnType<typeof useCompleteOnboarding>);
});

describe("ProfileForm", () => {
  it("submits the edited weight unit and coach notes", async () => {
    const user = userEvent.setup();
    render(
      <ProfileForm profile={{ weight_unit: "lbs", coach_notes: null }} />,
    );

    await user.selectOptions(screen.getByLabelText(/weight unit/i), "kg");
    await user.type(screen.getByLabelText(/coach notes/i), "bad left knee");
    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(mutateUpdate).toHaveBeenCalledWith(
      { weight_unit: "kg", coach_notes: "bad left knee" },
      expect.anything(),
    );
  });

  it("completes onboarding after a successful save, only when asked to", async () => {
    mutateUpdate.mockImplementation((_body, opts) => opts.onSuccess());
    const user = userEvent.setup();
    render(
      <ProfileForm
        profile={{ weight_unit: "lbs", coach_notes: null }}
        completeOnboardingOnSave
      />,
    );

    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(mutateComplete).toHaveBeenCalled();
  });

  it("does not complete onboarding on a plain settings save", async () => {
    mutateUpdate.mockImplementation((_body, opts) => opts.onSuccess());
    const user = userEvent.setup();
    render(<ProfileForm profile={{ weight_unit: "lbs", coach_notes: null }} />);

    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(mutateComplete).not.toHaveBeenCalled();
  });
});
