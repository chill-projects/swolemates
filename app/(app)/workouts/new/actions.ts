"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { Database } from "@/lib/supabase/database.types";

type ActivityType = Database["public"]["Enums"]["activity_type"];

export type SetInput =
  | {
      setType: "reps";
      actualWeight: number;
      actualReps: number;
      isWarmup: boolean;
    }
  | {
      setType: "time";
      workSeconds: number;
      restSeconds: number | null;
      actualWeight: number | null;
      isWarmup: boolean;
    };

export type ExerciseEntry = {
  exerciseId: string;
  sets: SetInput[];
};

export async function saveStrengthWorkout(payload: {
  title: string;
  exercises: ExerciseEntry[];
}) {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const { data: workout, error: workoutError } = await supabase
    .from("workouts")
    .insert({
      user_id: user.id,
      workout_type: "strength",
      title: payload.title || null,
      completed_at: new Date().toISOString(),
    })
    .select("id")
    .single();

  if (workoutError) {
    throw new Error(workoutError.message);
  }

  for (const [index, exercise] of payload.exercises.entries()) {
    const { data: workoutExercise, error: exerciseError } = await supabase
      .from("workout_exercises")
      .insert({
        workout_id: workout.id,
        exercise_id: exercise.exerciseId,
        order_index: index,
      })
      .select("id")
      .single();

    if (exerciseError) {
      throw new Error(exerciseError.message);
    }

    const setsToInsert = exercise.sets.map((set, setIndex) =>
      set.setType === "reps"
        ? {
            workout_exercise_id: workoutExercise.id,
            set_number: setIndex + 1,
            set_type: "reps" as const,
            actual_weight: set.actualWeight,
            actual_reps: set.actualReps,
            is_warmup: set.isWarmup,
          }
        : {
            workout_exercise_id: workoutExercise.id,
            set_number: setIndex + 1,
            set_type: "time" as const,
            work_seconds: set.workSeconds,
            rest_seconds: set.restSeconds,
            actual_weight: set.actualWeight,
            is_warmup: set.isWarmup,
          },
    );

    const { error: setsError } = await supabase
      .from("workout_sets")
      .insert(setsToInsert);

    if (setsError) {
      throw new Error(setsError.message);
    }
  }

  redirect(`/workouts/${workout.id}`);
}

export async function saveActivity(payload: {
  title: string;
  activityType: ActivityType;
  durationMinutes: number;
  notes: string;
}) {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const { data: workout, error } = await supabase
    .from("workouts")
    .insert({
      user_id: user.id,
      workout_type: "activity",
      activity_type: payload.activityType,
      duration_minutes: payload.durationMinutes,
      title: payload.title || null,
      notes: payload.notes || null,
      completed_at: new Date().toISOString(),
    })
    .select("id")
    .single();

  if (error) {
    throw new Error(error.message);
  }

  redirect(`/workouts/${workout.id}`);
}
