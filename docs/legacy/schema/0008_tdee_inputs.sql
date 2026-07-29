create type public.biological_sex as enum ('male', 'female');
create type public.activity_level as enum ('sedentary', 'light', 'moderate', 'active', 'very_active');
create type public.nutrition_goal_type as enum ('lose_weight', 'maintain', 'gain_muscle', 'recomp');

-- Inputs for the Mifflin-St Jeor TDEE calculation. Stored in imperial units
-- (height in total inches, weight in lbs) to match how the user enters
-- them — no metric round-trip needed since we use the imperial-equivalent
-- form of the formula.
alter table public.profiles
  add column sex public.biological_sex,
  add column age int,
  add column height_in numeric,
  add column weight_lbs numeric,
  add column activity_level public.activity_level,
  add column goal_type public.nutrition_goal_type;
