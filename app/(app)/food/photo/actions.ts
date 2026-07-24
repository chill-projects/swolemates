"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { FoodEstimateItem } from "@/app/api/food/estimate/route";

export type SavedFoodItem = FoodEstimateItem & { editedByUser: boolean };

export async function saveFoodEstimateItems(payload: {
  items: SavedFoodItem[];
  mealType: string;
}) {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const rows = payload.items.map((item) => ({
    user_id: user.id,
    source: "photo_ai" as const,
    name: item.name,
    serving_description: item.serving_description,
    calories: item.calories,
    protein_g: item.protein_g,
    carbs_g: item.carbs_g,
    fat_g: item.fat_g,
    fiber_g: item.fiber_g,
    confidence: item.confidence,
    raw_ai_response: item,
    edited_by_user: item.editedByUser,
    meal_type: payload.mealType || null,
  }));

  const { error } = await supabase.from("food_logs").insert(rows);

  if (error) {
    throw new Error(error.message);
  }

  redirect("/food");
}
