from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas.profile import ProfileOut, ProfileUpdate
from app.services import profile as service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut, operation_id="getProfile")
async def get_profile(user_sub: CurrentUser, session: DbSession) -> ProfileOut:
    profile = await service.get_or_create_profile(session, user_sub)
    return ProfileOut.model_validate(profile)


@router.patch("", response_model=ProfileOut, operation_id="updateProfile")
async def update_profile(
    body: ProfileUpdate, user_sub: CurrentUser, session: DbSession
) -> ProfileOut:
    try:
        profile = await service.update_profile(
            session,
            user_sub,
            weight_unit=body.weight_unit,
            coach_notes=body.coach_notes,
            sex=body.sex,
            age=body.age,
            height_in=body.height_in,
            activity_level=body.activity_level,
            goal_type=body.goal_type,
            timezone=body.timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProfileOut.model_validate(profile)


@router.post("/complete-onboarding", response_model=ProfileOut, operation_id="completeOnboarding")
async def complete_onboarding(user_sub: CurrentUser, session: DbSession) -> ProfileOut:
    profile = await service.complete_onboarding(session, user_sub)
    return ProfileOut.model_validate(profile)
