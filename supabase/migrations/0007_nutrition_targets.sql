-- Fiber wasn't tracked before — nullable since existing entries have no
-- retroactive data; treated as 0 in aggregations.
alter table public.food_logs
  add column fiber_g numeric;

-- Manually-set daily nutrition targets. All nullable — until a user sets
-- these, the app falls back to plain logged/not-logged tracking instead of
-- hit/miss-goal coloring.
alter table public.profiles
  add column calorie_target numeric,
  add column protein_target numeric,
  add column carb_target numeric,
  add column fat_target numeric,
  add column fiber_target numeric;
