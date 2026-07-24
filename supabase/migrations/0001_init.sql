-- Profiles: one row per auth.users, created automatically on signup.
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text not null,
  avatar_url text,
  goal text,
  secondary_goal text,
  current_routine text,
  onboarding_completed_at timestamptz,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "own profile rw" on public.profiles
  for all
  using (id = auth.uid())
  with check (id = auth.uid());

-- Auto-create a bare profile row whenever a new auth.users row is created.
create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1)));
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
