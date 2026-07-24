import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";

export default async function WorkoutsPage() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: workouts } = await supabase
    .from("workouts")
    .select("id, title, started_at, completed_at, workout_type, activity_type")
    .eq("user_id", user!.id)
    .order("started_at", { ascending: false });

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 px-4 py-8">
      <div className="flex items-baseline justify-between">
        <h1 className="font-display text-2xl font-semibold">Workouts</h1>
        <Link
          href="/workouts/new"
          className="rounded-full bg-teal px-4 py-2 text-sm font-medium text-white"
        >
          Log workout
        </Link>
      </div>

      {!workouts || workouts.length === 0 ? (
        <Card className="border-dashed text-center text-sm text-ink-soft">
          <div className="mb-1 font-display text-lg text-ink">
            No workouts yet
          </div>
          Log your first session to get started.
        </Card>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {workouts.map((workout) => {
            const isActivity = workout.workout_type === "activity";
            const label =
              workout.title || (isActivity ? workout.activity_type : "Workout");

            return (
              <li key={workout.id}>
                <Link href={`/workouts/${workout.id}`}>
                  <Card className="flex items-center justify-between hover:border-teal">
                    <div>
                      <span
                        className={`mr-2 rounded-full px-2 py-0.5 font-mono text-[10px] tracking-wide uppercase ${
                          isActivity
                            ? "bg-plum-pale text-plum"
                            : "bg-teal-pale text-teal"
                        }`}
                      >
                        {isActivity ? "activity" : "strength"}
                      </span>
                      <span className="font-semibold">{label}</span>
                    </div>
                    <span className="font-mono text-xs text-ink-soft">
                      {new Date(workout.started_at).toLocaleDateString()}
                    </span>
                  </Card>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
