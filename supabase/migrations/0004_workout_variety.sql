create type public.workout_type as enum ('strength', 'activity');
create type public.activity_type as enum ('yoga', 'pilates', 'cardio', 'other');
create type public.set_type as enum ('reps', 'time');

alter table public.workouts
  add column workout_type public.workout_type not null default 'strength',
  add column activity_type public.activity_type,
  add column duration_minutes integer;

alter table public.workouts
  add constraint workout_type_fields_check check (
    (workout_type = 'strength' and activity_type is null and duration_minutes is null)
    or (workout_type = 'activity' and activity_type is not null and duration_minutes is not null)
  );

-- Time-based (interval) sets don't have reps, and may not have an external
-- weight (bodyweight interval work) — relax both to nullable, enforced
-- instead by the set_type check below.
alter table public.workout_sets
  alter column actual_weight drop not null,
  alter column actual_reps drop not null;

alter table public.workout_sets
  add column set_type public.set_type not null default 'reps',
  add column work_seconds integer,
  add column rest_seconds integer;

alter table public.workout_sets
  add constraint set_type_fields_check check (
    (set_type = 'reps' and actual_reps is not null)
    or (set_type = 'time' and work_seconds is not null)
  );
