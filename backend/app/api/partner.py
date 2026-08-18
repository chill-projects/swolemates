from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas.partner import (
    InvitePreviewOut,
    PartnerInviteOut,
    PartnerSummaryOut,
    RedeemInviteRequest,
)
from app.services import partner as service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/partner", tags=["partner"])


@router.post("/invite", response_model=PartnerInviteOut, operation_id="generatePartnerInvite")
async def generate_invite(user_sub: CurrentUser, session: DbSession) -> PartnerInviteOut:
    try:
        invite = await service.generate_invite(session, user_sub)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PartnerInviteOut.model_validate(invite)


@router.get(
    "/invite/{code}", response_model=InvitePreviewOut, operation_id="getPartnerInvitePreview"
)
async def get_invite_preview(code: str, session: DbSession) -> InvitePreviewOut:
    """Unauthenticated by design — no `CurrentUser`/`CurrentPrincipal` parameter, same
    pattern as `/auth/config`. An unauthenticated visitor has to see this before
    signing up, and never anything more than a name and a validity flag."""
    inviter_display_name, valid = await service.get_invite_preview(session, code)
    return InvitePreviewOut(inviter_display_name=inviter_display_name, valid=valid)


@router.post("/redeem", response_model=PartnerSummaryOut, operation_id="redeemPartnerInvite")
async def redeem_invite(
    body: RedeemInviteRequest, user_sub: CurrentUser, session: DbSession
) -> PartnerSummaryOut:
    try:
        partner_user_sub = await service.redeem_invite(session, user_sub, body.code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    summary = await service.get_partner_summary(session, user_sub, partner_user_sub)
    return PartnerSummaryOut.model_validate(summary)


@router.get("", response_model=PartnerSummaryOut | None, operation_id="getPartnerSummary")
async def get_partner(user_sub: CurrentUser, session: DbSession) -> PartnerSummaryOut | None:
    partner_user_sub = await service.get_partner_user_id(session, user_sub)
    if partner_user_sub is None:
        return None
    try:
        summary = await service.get_partner_summary(session, user_sub, partner_user_sub)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PartnerSummaryOut.model_validate(summary)
