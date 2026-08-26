import asyncio
import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app import events
from app.deps import CurrentUser, DbSession
from app.schemas.workouts import (
    ExerciseOut,
    FinishWorkoutRequest,
    LogActivityRequest,
    LogSetRequest,
    LogSetResponse,
    LogWorkoutRequest,
    StartWorkoutRequest,
    StreakOut,
    UpdateWorkoutEntryRequest,
    WorkoutLiveOut,
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
    try:
        workout = await service.start_workout(
            session,
            user_sub,
            exercises=body.exercises,
            template_id=body.template_id,
            planned_id=body.planned_id,
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
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


@router.post("/{workout_id}/finish", response_model=WorkoutOut | None, operation_id="finishWorkout")
async def finish_workout(
    workout_id: uuid.UUID, body: FinishWorkoutRequest, user_sub: CurrentUser, session: DbSession
) -> WorkoutOut | None:
    try:
        workout = await service.finish_workout(
            session, user_sub, workout_id=workout_id, notes=body.notes
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # None means finish_workout discarded it (no exercises were ever added) rather
    # than persisting an empty completed row.
    return WorkoutOut.model_validate(workout) if workout else None


@router.delete("/{workout_id}", status_code=204, operation_id="deleteWorkout")
async def delete_workout(workout_id: uuid.UUID, user_sub: CurrentUser, session: DbSession) -> None:
    try:
        await service.delete_workout(session, user_sub, workout_id)
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/streak", response_model=StreakOut, operation_id="getWorkoutStreak")
async def get_workout_streak(user_sub: CurrentUser, session: DbSession) -> StreakOut:
    return StreakOut.model_validate(await service.get_streak(session, user_sub))


@router.get("/active", response_model=WorkoutOut | None, operation_id="getActiveWorkout")
async def get_active_workout(user_sub: CurrentUser, session: DbSession) -> WorkoutOut | None:
    workout = await service.get_active_workout(session, user_sub)
    return WorkoutOut.model_validate(workout) if workout else None


@router.get("/exercises", response_model=list[ExerciseOut], operation_id="listWorkoutExercises")
async def list_exercises(user_sub: CurrentUser, session: DbSession) -> list[ExerciseOut]:
    exercises = await service.list_exercises(session, user_sub)
    return [ExerciseOut.model_validate(e) for e in exercises]


@router.get("/{workout_id}/live", response_model=WorkoutLiveOut, operation_id="getWorkoutLive")
async def get_workout_live(
    workout_id: uuid.UUID, user_sub: CurrentUser, session: DbSession
) -> WorkoutLiveOut:
    try:
        workout = await service.get_workout(session, user_sub, workout_id)
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    live = await service.get_workout_live(session, user_sub, workout)
    return WorkoutLiveOut.model_validate(live)


@router.post(
    "/{workout_id}/entries", response_model=WorkoutLiveOut, operation_id="updateWorkoutEntry"
)
async def update_workout_entry(
    workout_id: uuid.UUID,
    body: UpdateWorkoutEntryRequest,
    user_sub: CurrentUser,
    session: DbSession,
) -> WorkoutLiveOut:
    try:
        workout = await service.update_workout_entry(
            session,
            user_sub,
            workout_id=workout_id,
            action=body.action,
            exercise=body.exercise,
            workout_exercise_id=body.workout_exercise_id,
            workout_set_id=body.workout_set_id,
            superset_with=body.superset_with,
            order=body.order,
            note=body.note,
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    live = await service.get_workout_live(session, user_sub, workout)
    return WorkoutLiveOut.model_validate(live)


@router.get("/events", operation_id="workoutsEvents", include_in_schema=False)
async def workouts_events(user_sub: CurrentUser) -> StreamingResponse:
    """Server-sent events: one `changed` event per mutation to this user's workout
    data. Events carry no data — clients refetch through the normal authz'd path.
    Excluded from the OpenAPI schema because the generated client can't type a
    stream; the SPA consumes it with a raw fetch (nutrition's pattern)."""

    async def stream():
        yield "retry: 3000\n\n"
        async with events.subscribe(user_sub) as queue:
            while True:
                try:
                    topic = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"event: changed\ndata: {topic}\n\n"
                except TimeoutError:
                    yield ": heartbeat\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
