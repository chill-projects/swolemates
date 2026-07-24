import { createClient } from "@/lib/supabase/server";
import { TargetsForm } from "./TargetsForm";

export default async function TargetsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: profile } = await supabase
    .from("profiles")
    .select(
      "sex, age, height_in, weight_lbs, activity_level, goal_type, calorie_target, protein_target, carb_target, fat_target, fiber_target",
    )
    .eq("id", user!.id)
    .single();

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-4 px-4 py-8">
      <h1 className="font-display text-2xl font-semibold">Daily targets</h1>
      <p className="text-sm text-ink-soft">
        Used to color your consistency calendar — a day is marked &quot;hit&quot;
        when you stayed within your calorie target and hit your protein
        target.
      </p>

      {error && (
        <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
          {error}
        </p>
      )}

      <TargetsForm profile={profile} />
    </div>
  );
}
