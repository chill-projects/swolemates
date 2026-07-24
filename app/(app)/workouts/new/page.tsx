import { createClient } from "@/lib/supabase/server";
import { NewWorkoutClient } from "./NewWorkoutClient";

export default async function NewWorkoutPage() {
  const supabase = await createClient();

  const { data: exercises } = await supabase
    .from("exercises")
    .select("id, name, muscle_group")
    .order("muscle_group")
    .order("name");

  return <NewWorkoutClient exercises={exercises ?? []} />;
}
