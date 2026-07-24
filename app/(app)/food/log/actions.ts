"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export async function logFood(payload: {
  name: string;
  servingDescription: string;
  calories: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
  fiberG: number | null;
  mealType: string;
  barcode: string;
}) {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const { error } = await supabase.from("food_logs").insert({
    user_id: user.id,
    source: "text_search",
    source_ref: payload.barcode,
    name: payload.name,
    serving_description: payload.servingDescription,
    calories: payload.calories,
    protein_g: payload.proteinG,
    carbs_g: payload.carbsG,
    fat_g: payload.fatG,
    fiber_g: payload.fiberG,
    meal_type: payload.mealType || null,
  });

  if (error) {
    throw new Error(error.message);
  }

  redirect("/food");
}
