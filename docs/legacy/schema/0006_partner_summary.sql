-- Partner-safe workout aggregate. SECURITY DEFINER so it can read the
-- target user's workouts (bypassing their owner-only RLS policy) but only
-- ever returns streak/frequency counts — never a row from workouts,
-- food_logs, or weight_entries. The exists() check is the actual security
-- boundary: it verifies the caller is linked to the target before anything
-- is computed.
create function public.get_partner_workout_summary(target_partner_id uuid)
returns table (
  current_streak_days int,
  workouts_last_7_days int,
  workouts_last_30_days int,
  total_workouts int,
  last_workout_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
begin
  if not exists (
    select 1 from public.partner_links
    where (user_id_a = auth.uid() and user_id_b = target_partner_id)
       or (user_id_b = auth.uid() and user_id_a = target_partner_id)
  ) then
    raise exception 'Not linked to this user.';
  end if;

  return query
  with days as (
    select distinct date(w.completed_at) as d
    from public.workouts w
    where w.user_id = target_partner_id and w.completed_at is not null
  ),
  grouped as (
    select d, d - (row_number() over (order by d))::int as grp
    from days
  ),
  last_day as (
    select max(d) as d from days
  ),
  streak as (
    select count(*) as n
    from grouped
    join last_day on grouped.d = last_day.d
  )
  select
    case
      when (select d from last_day) is null or (select d from last_day) < current_date - 1
      then 0
      else coalesce((select n from streak), 0)
    end,
    (select count(*)::int from days where d >= current_date - 7),
    (select count(*)::int from days where d >= current_date - 30),
    (select count(*)::int from public.workouts where user_id = target_partner_id and completed_at is not null),
    (select max(completed_at) from public.workouts where user_id = target_partner_id);
end;
$$;

grant execute on function public.get_partner_workout_summary to authenticated;
