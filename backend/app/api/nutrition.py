import asyncio
from datetime import date

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app import events
from app.deps import CurrentUser, DbSession
from app.schemas.nutrition import (
    GoalOut,
    LogNutritionRequest,
    LogOut,
    NutritionDayOut,
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


@router.get("/day", response_model=NutritionDayOut, operation_id="getNutritionDay")
async def get_nutrition_day(
    user_sub: CurrentUser, session: DbSession, day: date | None = None
) -> NutritionDayOut:
    return NutritionDayOut.model_validate(
        await service.get_nutrition_day(session, user_sub, day=day)
    )


@router.get("/events", operation_id="nutritionEvents", include_in_schema=False)
async def nutrition_events(user_sub: CurrentUser) -> StreamingResponse:
    """Server-sent events: one `changed` event per mutation to this user's nutrition
    data. Events carry no data — clients refetch through the normal authz'd path.
    Excluded from the OpenAPI schema because the generated client can't type a
    stream; the SPA consumes it with a raw fetch (tmpx's pattern)."""

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
