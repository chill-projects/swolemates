from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas.workouts import LogActivityRequest, LogWorkoutRequest, WorkoutOut
from app.services import workouts as service

router = APIRouter(prefix="/workouts", tags=["workouts"])


@router.post("/log", response_model=WorkoutOut, status_code=201, operation_id="logWorkout")
async def log_workout(
    body: LogWorkoutRequest, user_sub: CurrentUser, session: DbSession
) -> WorkoutOut:
    try:
        workout = await service.log_workout(
            session,
            user_sub,
            exercises=[e.model_dump() for e in body.exercises],
            title=body.title,
            notes=body.notes,
            logged_at=body.logged_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return WorkoutOut.model_validate(workout)


@router.post(
    "/log-activity", response_model=WorkoutOut, status_code=201, operation_id="logActivity"
)
async def log_activity(
    body: LogActivityRequest, user_sub: CurrentUser, session: DbSession
) -> WorkoutOut:
    try:
        workout = await service.log_activity(
            session,
            user_sub,
            activity_type=body.activity_type,
            duration_minutes=body.duration_minutes,
            title=body.title,
            notes=body.notes,
            logged_at=body.logged_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return WorkoutOut.model_validate(workout)


@router.get("", response_model=list[WorkoutOut], operation_id="getWorkoutHistory")
async def get_workout_history(
    user_sub: CurrentUser,
    session: DbSession,
    start: date | None = None,
    end: date | None = None,
    exercise: str | None = None,
) -> list[WorkoutOut]:
    workouts = await service.get_workout_history(
        session, user_sub, start=start, end=end, exercise=exercise
    )
    return [WorkoutOut.model_validate(w) for w in workouts]
