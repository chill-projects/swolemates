-- Guards the atomicity of public.save_strength_workout(): a strength
-- workout's tables (workouts -> workout_exercises -> workout_sets) must
-- persist all-or-nothing. Before this RPC existed, the write was three
-- separate client-side round trips with no transaction, so a failure on
-- e.g. the 2nd exercise left the workout and 1st exercise permanently
-- committed — a partial, silently-incomplete workout.
begin;
select plan(4);

-- Fixture: a test user (inserting into auth.users triggers the
-- handle_new_user() function, which creates the matching profiles row).
insert into auth.users (id, email)
values ('11111111-1111-1111-1111-111111111111', 'tdd-fixture@example.com');

-- Simulate being logged in as this user, since save_strength_workout()
-- derives the owner from auth.uid(), not a client-supplied user id.
-- auth.uid() only reads this JWT-claims setting, not the Postgres role, so
-- we stay as postgres here rather than switching to `authenticated` (which
-- has no grants on public.exercises locally — auto_expose_new_tables is off
-- by default; a separate, pre-existing gap, not something this test needs
-- to route around by granting privileges).
set local "request.jwt.claims" to '{"sub":"11111111-1111-1111-1111-111111111111","role":"authenticated"}';

-- Test 1: a fully valid payload persists the whole tree.
select public.save_strength_workout(
  jsonb_build_object(
    'title', 'tdd valid',
    'exercises', jsonb_build_array(
      jsonb_build_object(
        'exerciseId', (select id from public.exercises where name = 'Barbell Back Squat'),
        'sets', jsonb_build_array(
          jsonb_build_object('setType', 'reps', 'actualWeight', 135, 'actualReps', 5, 'isWarmup', false)
        )
      )
    )
  )
);

select isnt(
  (select id from public.workouts where title = 'tdd valid'),
  null,
  'valid payload creates a workout row'
);

select is(
  (
    select count(*)::int
    from public.workout_sets ws
    join public.workout_exercises we on we.id = ws.workout_exercise_id
    join public.workouts w on w.id = we.workout_id
    where w.title = 'tdd valid'
  ),
  1,
  'valid payload creates the expected workout_sets row'
);

-- Test 2: a payload whose 2nd exercise has a nonexistent exercise_id must
-- fail entirely (FK violation) and roll back the 1st exercise + the
-- workout row too — not leave them committed.
select throws_ok(
  format(
    $sql$
      select public.save_strength_workout('{
        "title": "tdd broken",
        "exercises": [
          {"exerciseId": "%s", "sets": [
            {"setType": "reps", "actualWeight": 100, "actualReps": 5, "isWarmup": false}
          ]},
          {"exerciseId": "00000000-0000-0000-0000-000000000099", "sets": [
            {"setType": "reps", "actualWeight": 50, "actualReps": 5, "isWarmup": false}
          ]}
        ]
      }'::jsonb)
    $sql$,
    (select id from public.exercises where name = 'Barbell Bench Press')
  ),
  '23503'::character(5),
  null,
  'a mid-list bad exercise_id raises a foreign key violation'
);

select is(
  (select count(*)::int from public.workouts where title = 'tdd broken'),
  0,
  'no partial workout row persists after a mid-list failure'
);

select * from finish();
rollback;
