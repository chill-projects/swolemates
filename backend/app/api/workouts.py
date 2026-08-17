import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas.workouts import (
    FinishWorkoutRequest,
    LogActivityRequest,
    LogSetRequest,
    LogSetResponse,
    LogWorkoutRequest,
    StartWorkoutRequest,
    WorkoutOut,
)
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


@router.post("/start", response_model=WorkoutOut, status_code=201, operation_id="startWorkout")
async def start_workout(
    body: StartWorkoutRequest, user_sub: CurrentUser, session: DbSession
) -> WorkoutOut:
    workout = await service.start_workout(session, user_sub, exercises=body.exercises)
    return WorkoutOut.model_validate(workout)


@router.post("/log-set", response_model=LogSetResponse, operation_id="logSet")
async def log_set(body: LogSetRequest, user_sub: CurrentUser, session: DbSession) -> LogSetResponse:
    try:
        result = await service.log_set(
            session,
            user_sub,
            exercise=body.exercise,
            reps=body.reps,
            weight=body.weight,
            set_type=body.set_type,
            work_seconds=body.work_seconds,
            is_warmup=body.is_warmup,
            sets=body.sets,
            note=body.note,
            continue_session=body.continue_session,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return LogSetResponse(
        workout=WorkoutOut.model_validate(result.workout) if result.workout else None,
        needs_clarification=result.needs_clarification,
    )


@router.post("/{workout_id}/finish", response_model=WorkoutOut, operation_id="finishWorkout")
async def finish_workout(
    workout_id: uuid.UUID, body: FinishWorkoutRequest, user_sub: CurrentUser, session: DbSession
) -> WorkoutOut:
    try:
        workout = await service.finish_workout(
            session, user_sub, workout_id=workout_id, notes=body.notes
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return WorkoutOut.model_validate(workout)


@router.get("/active", response_model=WorkoutOut | None, operation_id="getActiveWorkout")
async def get_active_workout(user_sub: CurrentUser, session: DbSession) -> WorkoutOut | None:
    workout = await service.get_active_workout(session, user_sub)
    return WorkoutOut.model_validate(workout) if workout else None
