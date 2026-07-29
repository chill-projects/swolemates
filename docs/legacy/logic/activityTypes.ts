import type { Database } from "@/lib/supabase/database.types";

export type ActivityType = Database["public"]["Enums"]["activity_type"];

export const ACTIVITY_TYPES: { value: ActivityType; label: string }[] = [
  { value: "yoga", label: "Yoga" },
  { value: "pilates", label: "Pilates" },
  { value: "cardio", label: "Cardio" },
  { value: "other", label: "Other" },
];

export function activityLabel(type: string | null): string {
  return ACTIVITY_TYPES.find((t) => t.value === type)?.label ?? "Activity";
}
