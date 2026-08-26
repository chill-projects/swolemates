import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useGoals, useLogWeight, useSetGoals } from "../api/nutrition";
import { useCalculateTargets, useCompleteOnboarding, useUpdateProfile } from "../api/profile";
import { ProfileForm } from "./ProfileForm";

vi.mock("../api/profile", () => ({
  useUpdateProfile: vi.fn(),
  useCompleteOnboarding: vi.fn(),
  useCalculateTargets: vi.fn(),
}));

vi.mock("../api/nutrition", () => ({
  useLogWeight: vi.fn(),
  useGoals: vi.fn(),
  useSetGoals: vi.fn(),
}));

const mutateUpdate = vi.fn();
const mutateComplete = vi.fn();
const mutateCalculate = vi.fn();
const mutateLogWeight = vi.fn();
const mutateSetGoals = vi.fn();

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
  vi.mocked(useCalculateTargets).mockReturnValue({
    mutate: mutateCalculate,
    isPending: false,
    isSuccess: false,
    isError: false,
  } as unknown as ReturnType<typeof useCalculateTargets>);
  vi.mocked(useLogWeight).mockReturnValue({
    mutate: mutateLogWeight,
    isPending: false,
    isSuccess: false,
    isError: false,
  } as unknown as ReturnType<typeof useLogWeight>);
  vi.mocked(useGoals).mockReturnValue({
    data: undefined,
  } as unknown as ReturnType<typeof useGoals>);
  vi.mocked(useSetGoals).mockReturnValue({
    mutate: mutateSetGoals,
    isPending: false,
    isSuccess: false,
    isError: false,
  } as unknown as ReturnType<typeof useSetGoals>);
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

  it("submits TDEE stats alongside weight unit and coach notes", async () => {
    const user = userEvent.setup();
    render(<ProfileForm profile={{ weight_unit: "lbs", coach_notes: null }} />);

    await user.selectOptions(screen.getByLabelText(/^sex$/i), "female");
    await user.type(screen.getByLabelText(/^age$/i), "25");
    await user.type(screen.getByLabelText(/height \(ft\)/i), "5");
    await user.type(screen.getByLabelText(/height \(in\)/i), "2");
    await user.selectOptions(screen.getByLabelText(/activity level/i), "moderate");
    await user.selectOptions(screen.getByLabelText(/^goal$/i), "recomp");
    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(mutateUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        sex: "female",
        age: 25,
        height_in: 62,
        activity_level: "moderate",
        goal_type: "recomp",
      }),
      expect.anything(),
    );
  });

  it("calculates targets when the button is clicked", async () => {
    const user = userEvent.setup();
    render(<ProfileForm profile={{ weight_unit: "lbs", coach_notes: null }} />);

    await user.click(screen.getByRole("button", { name: /calculate targets/i }));

    expect(mutateCalculate).toHaveBeenCalled();
  });

  it("shows the calculated targets on success, as editable fields", async () => {
    const data = { tdee: 1997, calories: 1697, protein_g: 117, carbs_g: 193, fat_g: 51, fiber_g: 24 };
    mutateCalculate.mockImplementation((_vars, options) => options?.onSuccess?.(data));
    vi.mocked(useCalculateTargets).mockReturnValue({
      mutate: mutateCalculate,
      isPending: false,
      isSuccess: true,
      isError: false,
      data,
    } as unknown as ReturnType<typeof useCalculateTargets>);

    const user = userEvent.setup();
    render(<ProfileForm profile={{ weight_unit: "lbs", coach_notes: null }} />);
    await user.click(screen.getByRole("button", { name: /calculate targets/i }));

    expect(screen.getByText(/1,997 cal\/day/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/protein/i)).toHaveValue(117);
    expect(screen.getByLabelText(/^calories$/i)).toHaveValue(1697);
  });

  it("redistributes carbs/fat/fiber when the calorie target is edited, protein fixed", async () => {
    const data = { tdee: 1997, calories: 1697, protein_g: 117, carbs_g: 193, fat_g: 51, fiber_g: 24 };
    mutateCalculate.mockImplementation((_vars, options) => options?.onSuccess?.(data));
    vi.mocked(useCalculateTargets).mockReturnValue({
      mutate: mutateCalculate,
      isPending: false,
      isSuccess: true,
      isError: false,
      data,
    } as unknown as ReturnType<typeof useCalculateTargets>);

    const user = userEvent.setup();
    render(<ProfileForm profile={{ weight_unit: "lbs", coach_notes: null }} />);
    await user.click(screen.getByRole("button", { name: /calculate targets/i }));

    const calories = screen.getByLabelText(/^calories$/i);
    await user.clear(calories);
    await user.type(calories, "2000");

    // fat = 2000*0.27/9 = 60; carbs = (2000 - 117*4 - 60*9)/4 = (2000-468-540)/4 = 248;
    // fiber = 2000/1000*14 = 28. Protein stays at 117 — never touched by the cascade.
    expect(screen.getByLabelText(/fat/i)).toHaveValue(60);
    expect(screen.getByLabelText(/carbs/i)).toHaveValue(248);
    expect(screen.getByLabelText(/fiber/i)).toHaveValue(28);
    expect(screen.getByLabelText(/protein/i)).toHaveValue(117);
  });

  it("shows an error message when calculation fails", () => {
    vi.mocked(useCalculateTargets).mockReturnValue({
      mutate: mutateCalculate,
      isPending: false,
      isSuccess: false,
      isError: true,
      error: new Error("Need a bit more info before I can calculate targets: sex."),
    } as unknown as ReturnType<typeof useCalculateTargets>);

    render(<ProfileForm profile={{ weight_unit: "lbs", coach_notes: null }} />);

    expect(screen.getByText(/need a bit more info/i)).toBeInTheDocument();
  });
});
