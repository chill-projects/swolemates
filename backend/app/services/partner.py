"""Partner v1 (#5/#12, resolved) — one accountability partner per user, invite/link
mechanics ported from docs/legacy/schema/0002_partner_links.sql onto WorkOS subs.

`get_partner_summary`'s narrow return type is the actual privacy boundary (#12,
resolved): it verifies the link exists, then composes only aggregate-value helpers
(existing `get_streak`, new `get_workout_frequency`/`list_personal_records`/
`get_nutrition_streak`) — `PartnerSummary` has no field food logs or weight entries
could travel through, so a careless future query change has nowhere to put that data
even by accident.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner import (
    InviteStatus,
    PartnerInvite,
    PartnerLink,
    Partnership,
    PartnershipMember,
)
from app.services import celebrations
from app.services import nutrition as nutrition_service
from app.services import profile as profile_service
from app.services import workouts as workouts_service
from app.services.celebrations import FrequencyOut, StreakOut
from app.services.errors import NotFoundError
from app.services.workouts import PersonalRecordSummary

log = logging.getLogger(__name__)

INVITE_CODE_BYTES = 4  # secrets.token_hex(4) -> 8 hex chars, matching legacy's format
INVITE_EXPIRY = timedelta(days=7)


@dataclass
class PartnerSummary:
    partner_user_sub: str
    partner_display_name: str | None
    streak: StreakOut
    frequency: FrequencyOut
    nutrition_streak: int
    personal_records: list[PersonalRecordSummary]


async def get_partner_user_id(session: AsyncSession, user_sub: str) -> str | None:
    """Reads `partnership_members`, never `partner_links` — see the model docstrings.

    Takes the oldest membership rather than asserting there's exactly one (#40). The
    `UNIQUE(user_id)` constraint now makes two memberships unreachable, but this call
    sits under all three partner endpoints, and the previous `scalar_one_or_none()`
    turned "somehow two rows" into a `MultipleResultsFound` on *every* subsequent
    partner request — a permanent 500 for that account with no retry or restart that
    recovers it. Degrading to the older link and saying so in the log is the behaviour
    worth having under an invariant this load-bearing.
    """
    memberships = (
        (
            await session.execute(
                select(PartnershipMember.partnership_id)
                .where(PartnershipMember.user_id == user_sub)
                .order_by(PartnershipMember.created_at, PartnershipMember.id)
                .limit(2)
            )
        )
        .scalars()
        .all()
    )
    if not memberships:
        return None
    if len(memberships) > 1:
        log.warning("user %s belongs to more than one partnership — using the oldest", user_sub)

    return (
        (
            await session.execute(
                select(PartnershipMember.user_id)
                .where(
                    PartnershipMember.partnership_id == memberships[0],
                    PartnershipMember.user_id != user_sub,
                )
                .order_by(PartnershipMember.created_at, PartnershipMember.id)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def get_own_invite(session: AsyncSession, user_sub: str) -> PartnerInvite | None:
    """Most recent pending, unexpired invite the caller created, if any."""
    result = await session.execute(
        select(PartnerInvite)
        .where(
            PartnerInvite.inviter_id == user_sub,
            PartnerInvite.status == InviteStatus.pending,
            PartnerInvite.expires_at > datetime.now(UTC),
        )
        .order_by(PartnerInvite.created_at.desc())
    )
    return result.scalars().first()


async def generate_invite(session: AsyncSession, user_sub: str) -> PartnerInvite:
    """Returns the caller's existing pending/unexpired invite if one exists, rather
    than minting a new code every call — avoids orphaning a code they've already
    shared. Raises ValueError if already linked (one partner max, matching legacy's
    create_partner_invite check)."""
    if await get_partner_user_id(session, user_sub) is not None:
        raise ValueError("You already have a partner linked.")

    existing = await get_own_invite(session, user_sub)
    if existing is not None:
        return existing

    invite = PartnerInvite(
        inviter_id=user_sub,
        code=secrets.token_hex(INVITE_CODE_BYTES),
        status=InviteStatus.pending,
        expires_at=datetime.now(UTC) + INVITE_EXPIRY,
    )
    session.add(invite)
    await session.flush()
    return invite


async def _find_invite(
    session: AsyncSession, code: str, *, for_update: bool = False
) -> PartnerInvite | None:
    """`for_update` takes a row lock for the redeem path (#40). Two people tapping the
    same shared link used to both read `pending`, both pass the guard, and both write.
    Under `FOR UPDATE` the second redemption blocks until the first commits and then
    re-reads the committed row — so it sees `redeemed` and gets "this invite has
    already been used", which is what the guard always meant to say.

    Not used on the preview path, which is unauthenticated and read-only: locking a row
    for anyone who opens an invite link would be a free way to stall redemptions.
    """
    query = select(PartnerInvite).where(PartnerInvite.code == code)
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_invite_preview(session: AsyncSession, code: str) -> tuple[str | None, bool]:
    """Returns `(inviter_display_name, valid)` — mirrors legacy's `get_invite_preview`,
    never raises, so an unauthenticated visitor sees "this invite isn't valid" for any
    missing/redeemed/expired code rather than an error page."""
    invite = await _find_invite(session, code)
    if (
        invite is None
        or invite.status != InviteStatus.pending
        or invite.expires_at < datetime.now(UTC)
    ):
        return None, False
    profile = await profile_service.get_or_create_profile(session, invite.inviter_id)
    return profile.display_name, True


async def redeem_invite(session: AsyncSession, user_sub: str, code: str) -> str:
    """Returns the new partner's user_id. Ports the ordered checks from legacy's
    redeem_partner_invite: already-linked, code-not-found, self-invite, already-used,
    then expired (flipping the row to `expired` same as legacy did, rather than
    leaving a stale `pending` row past its own deadline).

    Those checks are still the source of the *messages*, but they are no longer what
    makes the outcome correct (#40). They decide in Python on rows read moments earlier,
    which two concurrent redemptions can both pass. Two things close that now:

    - the invite row is locked (`_find_invite(for_update=True)`), so two people
      redeeming the same shared code serialize and the second sees `redeemed`;
    - `UNIQUE(user_id)` on `partnership_members` rejects the write outright, which is
      what catches the case a lock can't — one person redeeming two *different* codes
      at once, where the transactions touch no row in common. That's write skew, and
      it isn't caught by `REPEATABLE READ` either; only the constraint sees it.

    The `IntegrityError` that second case raises is a race, not a bug, and it means
    exactly what the first guard means — so it's reported with the same words.
    """
    if await get_partner_user_id(session, user_sub) is not None:
        raise ValueError("You already have a partner linked.")

    invite = await _find_invite(session, code, for_update=True)
    if invite is None:
        raise ValueError("Invite code not found.")
    if invite.inviter_id == user_sub:
        raise ValueError("You cannot redeem your own invite.")
    if invite.status != InviteStatus.pending:
        raise ValueError("This invite has already been used.")
    if invite.expires_at < datetime.now(UTC):
        invite.status = InviteStatus.expired
        await session.flush()
        raise ValueError("This invite has expired.")

    partnership = Partnership()
    session.add(partnership)
    await session.flush()
    session.add_all(
        [
            PartnershipMember(partnership_id=partnership.id, user_id=invite.inviter_id),
            PartnershipMember(partnership_id=partnership.id, user_id=user_sub),
        ]
    )

    # Dual-write for the blue-green overlap only: the previous release reads
    # `partner_links` for its own already-linked guard, and would let one of these two
    # take a second partner during the seconds both versions serve traffic. Removed
    # with the table in the follow-up deploy.
    user_id_a, user_id_b = sorted((invite.inviter_id, user_sub))
    session.add(PartnerLink(user_id_a=user_id_a, user_id_b=user_id_b))

    invite.status = InviteStatus.redeemed
    invite.redeemed_by = user_sub
    invite.redeemed_at = datetime.now(UTC)
    try:
        await session.flush()
    except IntegrityError as exc:
        # The transaction is unusable after this, and every caller turns a ValueError
        # into a response rather than a crash — so unwind here instead of handing back
        # a poisoned session that fails again at commit.
        await session.rollback()
        raise ValueError("You already have a partner linked.") from exc
    return invite.inviter_id


async def get_partner_summary(
    session: AsyncSession, user_sub: str, partner_user_sub: str
) -> PartnerSummary:
    # Reads the membership table, like every other check — this is the privacy boundary
    # (#12), so it has to be asking the same source of truth `redeem_invite` writes, not
    # the compatibility copy in `partner_links` that the next deploy deletes.
    mine = (
        select(PartnershipMember.partnership_id)
        .where(PartnershipMember.user_id == user_sub)
        .scalar_subquery()
    )
    result = await session.execute(
        select(PartnershipMember.id)
        .where(
            PartnershipMember.partnership_id.in_(mine),
            PartnershipMember.user_id == partner_user_sub,
        )
        .limit(1)
    )
    if result.first() is None:
        raise NotFoundError(f"Not linked to {partner_user_sub}")

    profile = await profile_service.get_or_create_profile(session, partner_user_sub)
    return PartnerSummary(
        partner_user_sub=partner_user_sub,
        partner_display_name=profile.display_name,
        streak=await celebrations.get_streak(session, partner_user_sub),
        frequency=await celebrations.get_workout_frequency(session, partner_user_sub),
        nutrition_streak=await nutrition_service.get_nutrition_streak(session, partner_user_sub),
        personal_records=await workouts_service.list_personal_records(session, partner_user_sub),
    )
