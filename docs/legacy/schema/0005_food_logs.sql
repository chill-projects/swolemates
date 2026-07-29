create type public.food_source as enum ('barcode', 'text_search', 'photo_ai');

-- Strictly owner-only, no exceptions — not even the partner-summary RPC
-- pattern used for workouts touches this table. confidence/raw_ai_response
-- are unused until the photo-based logging milestone but included now so
-- the shape doesn't need to change later.
create table public.food_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  logged_at timestamptz not null default now(),
  meal_type text,
  source public.food_source not null,
  source_ref text,
  photo_storage_path text,
  name text not null,
  serving_description text,
  calories numeric not null,
  protein_g numeric not null,
  carbs_g numeric not null,
  fat_g numeric not null,
  confidence jsonb,
  raw_ai_response jsonb,
  edited_by_user boolean not null default false,
  created_at timestamptz not null default now()
);

alter table public.food_logs enable row level security;

create policy "own food_logs" on public.food_logs
  for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());
