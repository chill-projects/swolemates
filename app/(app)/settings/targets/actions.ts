"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { Database } from "@/lib/supabase/database.types";

type BiologicalSex = Database["public"]["Enums"]["biological_sex"];
type ActivityLevel = Database["public"]["Enums"]["activity_level"];
type GoalType = Database["public"]["Enums"]["nutrition_goal_type"];

export async function saveTargets(formData: FormData) {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  function num(name: string) {
    const value = formData.get(name);
    if (!value || value === "") return null;
    return Number(value);
  }

  function str(name: string) {
    const value = formData.get(name);
    return value && value !== "" ? (value as string) : null;
  }

  const { error } = await supabase
    .from("profiles")
    .update({
      sex: str("sex") as BiologicalSex | null,
      age: num("age"),
      height_in: num("heightIn"),
      weight_lbs: num("weightLbs"),
      activity_level: str("activityLevel") as ActivityLevel | null,
      goal_type: str("goalType") as GoalType | null,
      calorie_target: num("calorieTarget"),
      protein_target: num("proteinTarget"),
      carb_target: num("carbTarget"),
      fat_target: num("fatTarget"),
      fiber_target: num("fiberTarget"),
    })
    .eq("id", user.id);

  if (error) {
    redirect(`/settings/targets?error=${encodeURIComponent(error.message)}`);
  }

  redirect("/dashboard");
}
