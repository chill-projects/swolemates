create table public.exercises (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  muscle_group text not null,
  equipment text,
  is_custom boolean not null default false,
  created_by uuid references public.profiles (id),
  created_at timestamptz not null default now()
);

alter table public.exercises enable row level security;

create policy "read catalog" on public.exercises
  for select
  using (is_custom = false or created_by = auth.uid());

create policy "insert own custom" on public.exercises
  for insert
  with check (created_by = auth.uid() and is_custom = true);

create table public.workouts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  title text,
  notes text,
  created_at timestamptz not null default now()
);

alter table public.workouts enable row level security;

create policy "own workouts" on public.workouts
  for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create table public.workout_exercises (
  id uuid primary key default gen_random_uuid(),
  workout_id uuid not null references public.workouts (id) on delete cascade,
  exercise_id uuid not null references public.exercises (id),
  order_index int not null default 0,
  notes text
);

alter table public.workout_exercises enable row level security;

create policy "own workout_exercises" on public.workout_exercises
  for all
  using (
    exists (
      select 1 from public.workouts w
      where w.id = workout_id and w.user_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from public.workouts w
      where w.id = workout_id and w.user_id = auth.uid()
    )
  );

-- actual_weight / actual_reps are required (not nullable) — this is the
-- data v2's auto-progression logic will need to know whether a set was
-- actually hit, so it can't be optional even though we don't use it yet.
create table public.workout_sets (
  id uuid primary key default gen_random_uuid(),
  workout_exercise_id uuid not null references public.workout_exercises (id) on delete cascade,
  set_number int not null,
  prescribed_weight numeric,
  prescribed_reps int,
  actual_weight numeric not null,
  actual_reps int not null,
  is_warmup boolean not null default false,
  rpe numeric,
  completed_at timestamptz not null default now()
);

alter table public.workout_sets enable row level security;

create policy "own workout_sets" on public.workout_sets
  for all
  using (
    exists (
      select 1
      from public.workout_exercises we
      join public.workouts w on w.id = we.workout_id
      where we.id = workout_exercise_id and w.user_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1
      from public.workout_exercises we
      join public.workouts w on w.id = we.workout_id
      where we.id = workout_exercise_id and w.user_id = auth.uid()
    )
  );

insert into public.exercises (name, muscle_group, equipment) values
  ('Barbell Back Squat', 'legs', 'barbell'),
  ('Front Squat', 'legs', 'barbell'),
  ('Romanian Deadlift', 'legs', 'barbell'),
  ('Deadlift', 'back', 'barbell'),
  ('Hip Thrust', 'legs', 'barbell'),
  ('Bulgarian Split Squat', 'legs', 'dumbbell'),
  ('Walking Lunge', 'legs', 'dumbbell'),
  ('Leg Press', 'legs', 'machine'),
  ('Leg Curl', 'legs', 'machine'),
  ('Leg Extension', 'legs', 'machine'),
  ('Calf Raise', 'legs', 'machine'),
  ('Barbell Bench Press', 'chest', 'barbell'),
  ('Incline Barbell Press', 'chest', 'barbell'),
  ('Dumbbell Bench Press', 'chest', 'dumbbell'),
  ('Incline Dumbbell Press', 'chest', 'dumbbell'),
  ('Push-up', 'chest', 'bodyweight'),
  ('Cable Fly', 'chest', 'cable'),
  ('Chest Fly (Machine)', 'chest', 'machine'),
  ('Barbell Row', 'back', 'barbell'),
  ('Dumbbell Row', 'back', 'dumbbell'),
  ('Pull-up', 'back', 'bodyweight'),
  ('Chin-up', 'back', 'bodyweight'),
  ('Lat Pulldown', 'back', 'machine'),
  ('Seated Cable Row', 'back', 'machine'),
  ('Overhead Press', 'shoulders', 'barbell'),
  ('Dumbbell Shoulder Press', 'shoulders', 'dumbbell'),
  ('Arnold Press', 'shoulders', 'dumbbell'),
  ('Lateral Raise', 'shoulders', 'dumbbell'),
  ('Front Raise', 'shoulders', 'dumbbell'),
  ('Face Pull', 'shoulders', 'cable'),
  ('Barbell Curl', 'arms', 'barbell'),
  ('Dumbbell Curl', 'arms', 'dumbbell'),
  ('Hammer Curl', 'arms', 'dumbbell'),
  ('Close-Grip Bench Press', 'arms', 'barbell'),
  ('Skull Crusher', 'arms', 'barbell'),
  ('Tricep Pushdown', 'arms', 'machine'),
  ('Dip', 'arms', 'bodyweight'),
  ('Plank', 'core', 'bodyweight'),
  ('Hanging Leg Raise', 'core', 'bodyweight'),
  ('Cable Crunch', 'core', 'cable'),
  ('Russian Twist', 'core', 'bodyweight');
