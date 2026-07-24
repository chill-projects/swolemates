import { notFound } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";

export default async function WorkoutDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();

  const { data: workout } = await supabase
    .from("workouts")
    .select(
      `
      id,
      title,
      started_at,
      workout_type,
      activity_type,
      duration_minutes,
      notes,
      workout_exercises (
        id,
        order_index,
        exercises ( name ),
        workout_sets ( id, set_number, set_type, actual_weight, actual_reps, work_seconds, rest_seconds, is_warmup )
      )
    `,
    )
    .eq("id", id)
    .single();

  if (!workout) {
    notFound();
  }

  if (workout.workout_type === "activity") {
    return (
      <div className="mx-auto flex max-w-lg flex-col gap-4 px-4 py-8">
        <h1 className="font-display text-2xl font-semibold">
          {workout.title || activityLabel(workout.activity_type)}
        </h1>
        <p className="font-mono text-xs tracking-wide text-ink-soft uppercase">
          {new Date(workout.started_at).toLocaleString()}
        </p>
        <Card>
          <div className="font-display text-2xl font-semibold">
            {workout.duration_minutes}
            <span className="ml-1 font-mono text-sm font-normal text-ink-soft">
              min
            </span>
          </div>
          <div className="mt-1 font-mono text-xs text-ink-soft">
            {activityLabel(workout.activity_type)}
          </div>
        </Card>
        {workout.notes && <p className="text-sm text-ink-soft">{workout.notes}</p>}
      </div>
    );
  }

  const sortedExercises = [...workout.workout_exercises].sort(
    (a, b) => a.order_index - b.order_index,
  );

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 px-4 py-8">
      <h1 className="font-display text-2xl font-semibold">
        {workout.title || "Workout"}
      </h1>
      <p className="font-mono text-xs tracking-wide text-ink-soft uppercase">
        {new Date(workout.started_at).toLocaleString()}
      </p>

      {sortedExercises.map((entry) => (
        <Card key={entry.id}>
          <h2 className="font-semibold">{entry.exercises?.name}</h2>
          <ul className="mt-2 flex flex-col gap-1 font-mono text-sm text-ink-soft">
            {[...entry.workout_sets]
              .sort((a, b) => a.set_number - b.set_number)
              .map((set) => (
                <li key={set.id} className="flex gap-2">
                  <span className="w-6 text-ink-soft/70">{set.set_number}</span>
                  <span className="text-ink">
                    {set.set_type === "reps"
                      ? `${set.actual_weight} × ${set.actual_reps}`
                      : `${set.work_seconds}s on${
                          set.rest_seconds ? ` / ${set.rest_seconds}s off` : ""
                        }${set.actual_weight ? ` @ ${set.actual_weight}` : ""}`}
                    {set.is_warmup ? " (warmup)" : ""}
                  </span>
                </li>
              ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

function activityLabel(type: string | null) {
  switch (type) {
    case "yoga":
      return "Yoga";
    case "pilates":
      return "Pilates";
    case "cardio":
      return "Cardio";
    default:
      return "Activity";
  }
}
