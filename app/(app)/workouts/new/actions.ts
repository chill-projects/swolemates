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

  // Single RPC so the workout + all its exercises/sets persist as one
  // atomic transaction — see supabase/migrations/0010_save_strength_workout_rpc.sql.
  // A partway failure (e.g. a bad exercise) rolls back everything, instead
  // of leaving earlier exercises/sets permanently committed.
  const { data, error } = await supabase.rpc("save_strength_workout", {
    payload: {
      title: payload.title || null,
      exercises: payload.exercises.map((exercise) => ({
        exerciseId: exercise.exerciseId,
        sets: exercise.sets,
      })),
    },
  });

  if (error) {
    throw new Error(error.message);
  }

  redirect(`/workouts/${data[0].workout_id}`);
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
