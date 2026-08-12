from fastapi import APIRouter

from app.deps import CurrentUser, DbSession
from app.schemas.nutrition import (
    GoalOut,
    LogNutritionRequest,
    LogOut,
    SetGoalsRequest,
    TrackableTypeOut,
)
from app.services import nutrition as service

router = APIRouter(prefix="/nutrition", tags=["nutrition"])


@router.get(
    "/trackable-types", response_model=list[TrackableTypeOut], operation_id="listTrackableTypes"
)
async def list_trackable_types(session: DbSession) -> list[TrackableTypeOut]:
    types = await service.list_trackable_types(session)
    return [TrackableTypeOut.model_validate(t) for t in types]


@router.post("/logs", response_model=LogOut, status_code=201, operation_id="logNutrition")
async def log_nutrition(
    body: LogNutritionRequest, user_sub: CurrentUser, session: DbSession
) -> LogOut:
    log = await service.log_nutrition(
        session,
        user_sub,
        entries=[e.model_dump() for e in body.entries],
        logged_at=body.logged_at,
        name=body.name,
        meal_type=body.meal_type,
        source=body.source,
    )
    return LogOut.model_validate(log)


@router.get("/goals", response_model=list[GoalOut], operation_id="getGoals")
async def get_goals(user_sub: CurrentUser, session: DbSession) -> list[GoalOut]:
    goals = await service.get_goals(session, user_sub)
    return [GoalOut.model_validate(g) for g in goals]


@router.put("/goals", response_model=list[GoalOut], operation_id="setGoals")
async def set_goals(
    body: SetGoalsRequest, user_sub: CurrentUser, session: DbSession
) -> list[GoalOut]:
    goals = await service.set_goals(session, user_sub, goals=[g.model_dump() for g in body.goals])
    return [GoalOut.model_validate(g) for g in goals]
