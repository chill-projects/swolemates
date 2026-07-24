-- Persists a full strength workout (workouts -> workout_exercises ->
-- workout_sets) as a single atomic write. Previously this was three
-- separate client round trips with no transaction, so a failure partway
-- through (e.g. a bad exercise on the 2nd exercise) left the workout and
-- any earlier exercises permanently committed — a partial, silently-
-- incomplete workout. A single plpgsql function call is one transaction:
-- any exception (FK violation, CHECK violation, etc.) rolls back
-- everything inserted so far in this call, not just the failing insert.
create function public.save_strength_workout(payload jsonb)
returns table (workout_id uuid)
language plpgsql
security definer
set search_path = public
as $$
declare
  new_workout_id uuid;
  exercise jsonb;
  set_row jsonb;
  new_workout_exercise_id uuid;
  ex_index int := 0;
  set_index int;
begin
  insert into public.workouts (user_id, workout_type, title, completed_at)
  values (auth.uid(), 'strength', nullif(payload->>'title', ''), now())
  returning id into new_workout_id;

  for exercise in select * from jsonb_array_elements(payload->'exercises')
  loop
    insert into public.workout_exercises (workout_id, exercise_id, order_index)
    values (new_workout_id, (exercise->>'exerciseId')::uuid, ex_index)
    returning id into new_workout_exercise_id;

    set_index := 0;
    for set_row in select * from jsonb_array_elements(exercise->'sets')
    loop
      set_index := set_index + 1;

      if (set_row->>'setType') = 'reps' then
        insert into public.workout_sets (
          workout_exercise_id, set_number, set_type,
          actual_weight, actual_reps, is_warmup
        ) values (
          new_workout_exercise_id, set_index, 'reps',
          (set_row->>'actualWeight')::numeric,
          (set_row->>'actualReps')::int,
          coalesce((set_row->>'isWarmup')::boolean, false)
        );
      else
        insert into public.workout_sets (
          workout_exercise_id, set_number, set_type,
          work_seconds, rest_seconds, actual_weight, is_warmup
        ) values (
          new_workout_exercise_id, set_index, 'time',
          (set_row->>'workSeconds')::int,
          (set_row->>'restSeconds')::int,
          (set_row->>'actualWeight')::numeric,
          coalesce((set_row->>'isWarmup')::boolean, false)
        );
      end if;
    end loop;

    ex_index := ex_index + 1;
  end loop;

  return query select new_workout_id;
end;
$$;

grant execute on function public.save_strength_workout to authenticated;
