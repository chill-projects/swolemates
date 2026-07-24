create type public.invite_status as enum ('pending', 'redeemed', 'expired', 'revoked');

create table public.partner_invites (
  id uuid primary key default gen_random_uuid(),
  inviter_id uuid not null references public.profiles (id) on delete cascade,
  code text not null unique,
  status public.invite_status not null default 'pending',
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '7 days'),
  redeemed_by uuid references public.profiles (id),
  redeemed_at timestamptz
);

alter table public.partner_invites enable row level security;

-- Clients can read their own invites; all writes go through the RPCs below,
-- so there's deliberately no insert/update policy here.
create policy "own invites" on public.partner_invites
  for select
  using (inviter_id = auth.uid());

create table public.partner_links (
  id uuid primary key default gen_random_uuid(),
  user_id_a uuid not null references public.profiles (id) on delete cascade,
  user_id_b uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  constraint ordered_pair check (user_id_a < user_id_b),
  constraint unique_pair unique (user_id_a, user_id_b)
);

alter table public.partner_links enable row level security;

create policy "own link" on public.partner_links
  for select
  using (auth.uid() in (user_id_a, user_id_b));

-- Safe partner-visible slice of a profile: name + avatar only, and only for
-- someone you're actually linked to. security_invoker means this view
-- respects the caller's RLS, not the view owner's.
create view public.partner_profile_public
with (security_invoker = true) as
select p.id, p.display_name, p.avatar_url
from public.profiles p
join public.partner_links pl
  on (pl.user_id_a = p.id or pl.user_id_b = p.id)
where (pl.user_id_a = auth.uid() or pl.user_id_b = auth.uid())
  and p.id != auth.uid();

grant select on public.partner_profile_public to authenticated;

-- Generates a short invite code for the caller. Errors if the caller is
-- already linked to someone (one partner per user, matching the redeem
-- side's check below).
create function public.create_partner_invite()
returns table (code text)
language plpgsql
security definer
set search_path = public
as $$
declare
  new_code text;
begin
  if exists (
    select 1 from public.partner_links
    where auth.uid() in (user_id_a, user_id_b)
  ) then
    raise exception 'You are already linked to a partner.';
  end if;

  new_code := substr(replace(gen_random_uuid()::text, '-', ''), 1, 8);

  insert into public.partner_invites (inviter_id, code)
  values (auth.uid(), new_code);

  return query select new_code;
end;
$$;

grant execute on function public.create_partner_invite to authenticated;

-- Public preview for an unauthenticated visitor landing on /invite/{code} —
-- returns only the inviter's display name and whether the code is still
-- valid, never anything else about the inviter.
create function public.get_invite_preview(invite_code text)
returns table (inviter_display_name text, valid boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  inv public.partner_invites%rowtype;
begin
  select * into inv from public.partner_invites where code = invite_code;

  if inv is null or inv.status <> 'pending' or inv.expires_at < now() then
    return query select null::text, false;
    return;
  end if;

  return query
    select p.display_name, true
    from public.profiles p
    where p.id = inv.inviter_id;
end;
$$;

grant execute on function public.get_invite_preview to anon, authenticated;

-- Redeems an invite code for the calling (authenticated) user. Locks the
-- invite row for the duration of the transaction so two people can't redeem
-- the same code in a race.
create function public.redeem_partner_invite(invite_code text)
returns table (linked_with uuid)
language plpgsql
security definer
set search_path = public
as $$
declare
  inv public.partner_invites%rowtype;
  a uuid;
  b uuid;
begin
  if exists (
    select 1 from public.partner_links
    where auth.uid() in (user_id_a, user_id_b)
  ) then
    raise exception 'You are already linked to a partner.';
  end if;

  select * into inv
  from public.partner_invites
  where code = invite_code
  for update;

  if inv is null then
    raise exception 'Invite code not found.';
  end if;

  if inv.inviter_id = auth.uid() then
    raise exception 'You cannot redeem your own invite.';
  end if;

  if inv.status <> 'pending' then
    raise exception 'This invite has already been used.';
  end if;

  if inv.expires_at < now() then
    update public.partner_invites set status = 'expired' where id = inv.id;
    raise exception 'This invite has expired.';
  end if;

  a := least(inv.inviter_id, auth.uid());
  b := greatest(inv.inviter_id, auth.uid());

  insert into public.partner_links (user_id_a, user_id_b) values (a, b);

  update public.partner_invites
  set status = 'redeemed', redeemed_by = auth.uid(), redeemed_at = now()
  where id = inv.id;

  return query select inv.inviter_id;
end;
$$;

grant execute on function public.redeem_partner_invite to authenticated;
