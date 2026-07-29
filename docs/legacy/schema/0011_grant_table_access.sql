-- Every table in this schema currently has zero grants for `authenticated`
-- (confirmed via information_schema.role_table_grants on a fresh local
-- reset) — only the `partner_profile_public` view and the SECURITY DEFINER
-- RPCs are reachable. RLS policies restrict WHAT a role can touch; they
-- don't substitute for the base GRANT that lets the role touch the table at
-- all. Supabase's `auto_expose_new_tables` legacy default (auto-granting
-- new public-schema tables to anon/authenticated/service_role) is off by
-- default now (see the commented-out setting in supabase/config.toml), so
-- every table created since needs its grant spelled out explicitly instead
-- of relying on that default.
--
-- Grants below mirror each table's existing RLS policy shape: a "for all"
-- policy gets all four verbs; a table with only a SELECT policy (writes
-- deliberately routed through RPCs instead) gets SELECT only.

grant select, insert, update, delete on public.profiles to authenticated;
grant select, insert on public.exercises to authenticated;
grant select, insert, update, delete on public.workouts to authenticated;
grant select, insert, update, delete on public.workout_exercises to authenticated;
grant select, insert, update, delete on public.workout_sets to authenticated;
grant select, insert, update, delete on public.food_logs to authenticated;

-- partner_invites/partner_links: only a SELECT policy exists on each — all
-- writes go through create_partner_invite/redeem_partner_invite, so no
-- insert/update/delete grant here, matching that deliberate design.
grant select on public.partner_invites to authenticated;
grant select on public.partner_links to authenticated;
