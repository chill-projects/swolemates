import uuid
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas.planned_workouts import (
    PlannedWorkoutOut,
    PlanWorkoutRequest,
    SetWeeklyPatternRequest,
    UpdatePlannedWorkoutRequest,
    WeeklyPatternDayOut,
)
from app.services import planned_workouts as service

router = APIRouter(tags=["planned-workouts"])


@router.get(
    "/weekly-pattern", response_model=list[WeeklyPatternDayOut], operation_id="getWeeklyPattern"
)
async def get_weekly_pattern(
    user_sub: CurrentUser, session: DbSession
) -> list[WeeklyPatternDayOut]:
    days = await service.get_weekly_pattern(session, user_sub)
    return [WeeklyPatternDayOut.model_validate(d) for d in days]


@router.put(
    "/weekly-pattern", response_model=list[WeeklyPatternDayOut], operation_id="setWeeklyPattern"
)
async def set_weekly_pattern(
    body: SetWeeklyPatternRequest, user_sub: CurrentUser, session: DbSession
) -> list[WeeklyPatternDayOut]:
    try:
        days = await service.set_weekly_pattern(
            session, user_sub, days=[d.model_dump() for d in body.days]
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [WeeklyPatternDayOut.model_validate(d) for d in days]


@router.get(
    "/planned-workouts",
    response_model=list[PlannedWorkoutOut],
    operation_id="getPlannedWorkouts",
)
async def get_planned_workouts(
    user_sub: CurrentUser,
    session: DbSession,
    start: date | None = None,
    end: date | None = None,
) -> list[PlannedWorkoutOut]:
    range_start = start or date.today()
    range_end = end or (range_start + timedelta(days=6))
    planned = await service.get_planned_workouts(
        session, user_sub, start=range_start, end=range_end
    )
    return [PlannedWorkoutOut.model_validate(p) for p in planned]


@router.post(
    "/planned-workouts",
    response_model=PlannedWorkoutOut,
    status_code=201,
    operation_id="planWorkout",
)
async def plan_workout(
    body: PlanWorkoutRequest, user_sub: CurrentUser, session: DbSession
) -> PlannedWorkoutOut:
    try:
        planned = await service.plan_workout(
            session, user_sub, template_id=body.template_id, scheduled_for=body.scheduled_for
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlannedWorkoutOut.model_validate(planned)


@router.post(
    "/planned-workouts/{planned_id}/entries",
    response_model=PlannedWorkoutOut,
    operation_id="updatePlannedWorkout",
)
async def update_planned_workout(
    planned_id: uuid.UUID,
    body: UpdatePlannedWorkoutRequest,
    user_sub: CurrentUser,
    session: DbSession,
) -> PlannedWorkoutOut:
    try:
        planned = await service.update_planned_workout(
            session, user_sub, planned_id=planned_id, action=body.action
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlannedWorkoutOut.model_validate(planned)
