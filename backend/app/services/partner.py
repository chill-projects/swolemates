"""Partner v1 (#5/#12, resolved) — one accountability partner per user, invite/link
mechanics ported from docs/legacy/schema/0002_partner_links.sql onto WorkOS subs.

`get_partner_summary`'s narrow return type is the actual privacy boundary (#12,
resolved): it verifies the link exists, then composes only aggregate-value helpers
(existing `get_streak`, new `get_workout_frequency`/`list_personal_records`/
`get_nutrition_streak`) — `PartnerSummary` has no field food logs or weight entries
could travel through, so a careless future query change has nowhere to put that data
even by accident.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner import InviteStatus, PartnerInvite, PartnerLink
from app.services import celebrations
from app.services import nutrition as nutrition_service
from app.services import profile as profile_service
from app.services import workouts as workouts_service
from app.services.celebrations import FrequencyOut, StreakOut
from app.services.errors import NotFoundError
from app.services.workouts import PersonalRecordSummary

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
    result = await session.execute(
        select(PartnerLink).where(
            (PartnerLink.user_id_a == user_sub) | (PartnerLink.user_id_b == user_sub)
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        return None
    return link.user_id_b if link.user_id_a == user_sub else link.user_id_a


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


async def _find_invite(session: AsyncSession, code: str) -> PartnerInvite | None:
    result = await session.execute(select(PartnerInvite).where(PartnerInvite.code == code))
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
    leaving a stale `pending` row past its own deadline)."""
    if await get_partner_user_id(session, user_sub) is not None:
        raise ValueError("You already have a partner linked.")

    invite = await _find_invite(session, code)
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

    user_id_a, user_id_b = sorted((invite.inviter_id, user_sub))
    session.add(PartnerLink(user_id_a=user_id_a, user_id_b=user_id_b))
    invite.status = InviteStatus.redeemed
    invite.redeemed_by = user_sub
    invite.redeemed_at = datetime.now(UTC)
    await session.flush()
    return invite.inviter_id


async def get_partner_summary(
    session: AsyncSession, user_sub: str, partner_user_sub: str
) -> PartnerSummary:
    result = await session.execute(
        select(PartnerLink.id).where(
            ((PartnerLink.user_id_a == user_sub) & (PartnerLink.user_id_b == partner_user_sub))
            | ((PartnerLink.user_id_a == partner_user_sub) & (PartnerLink.user_id_b == user_sub))
        )
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
