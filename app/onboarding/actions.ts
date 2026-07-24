"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export async function completeOnboarding(formData: FormData) {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const { error } = await supabase
    .from("profiles")
    .update({
      goal: formData.get("goal") as string,
      secondary_goal: (formData.get("secondaryGoal") as string) || null,
      current_routine: (formData.get("currentRoutine") as string) || null,
      onboarding_completed_at: new Date().toISOString(),
    })
    .eq("id", user.id);

  if (error) {
    redirect(`/onboarding?error=${encodeURIComponent(error.message)}`);
  }

  redirect("/dashboard");
}
