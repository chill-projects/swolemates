import asyncio
import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app import events
from app.deps import CurrentUser, DbSession
from app.schemas.nutrition import (
    AmendLastLogOut,
    GoalOut,
    LogMealTemplateRequest,
    LogNutritionRequest,
    LogOut,
    MealTemplateSummaryOut,
    NutritionDayOut,
    NutritionLogOut,
    SaveMealTemplateRequest,
    SetGoalsRequest,
    TrackableTypeOut,
    UpdateMealTemplateItemRequest,
    UpdateNutritionLogRequest,
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


@router.patch("/logs/{log_id}", response_model=NutritionLogOut, operation_id="updateNutritionLog")
async def update_nutrition_log(
    log_id: uuid.UUID, body: UpdateNutritionLogRequest, user_sub: CurrentUser, session: DbSession
) -> NutritionLogOut:
    try:
        log = await service.update_nutrition_log(
            session,
            user_sub,
            log_id=log_id,
            name=body.name,
            meal_type=body.meal_type,
            values=body.values,
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_values = await service.get_log_values(session, user_sub, log.id)
    values = {v.trackable_key: v.value for v in log_values}
    return NutritionLogOut(
        id=log.id, name=log.name, logged_at=log.logged_at, meal_type=log.meal_type, values=values
    )


@router.post("/logs/amend-last", response_model=AmendLastLogOut, operation_id="amendLastLog")
async def amend_last_log(
    body: UpdateNutritionLogRequest, user_sub: CurrentUser, session: DbSession
) -> AmendLastLogOut:
    try:
        updated, log_id, _name = await service.amend_last_log(
            session, user_sub, name=body.name, meal_type=body.meal_type, values=body.values
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if updated is None:
        return AmendLastLogOut(deleted=True, log=None)
    log_values = await service.get_log_values(session, user_sub, log_id)
    values = {v.trackable_key: v.value for v in log_values}
    return AmendLastLogOut(
        deleted=False,
        log=NutritionLogOut(
            id=updated.id,
            name=updated.name,
            logged_at=updated.logged_at,
            meal_type=updated.meal_type,
            values=values,
        ),
    )


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


@router.get(
    "/templates", response_model=list[MealTemplateSummaryOut], operation_id="listMealTemplates"
)
async def list_meal_templates(
    user_sub: CurrentUser, session: DbSession
) -> list[MealTemplateSummaryOut]:
    templates = await service.list_meal_templates(session, user_sub)
    return [MealTemplateSummaryOut.model_validate(t) for t in templates]


@router.post(
    "/templates",
    response_model=MealTemplateSummaryOut,
    status_code=201,
    operation_id="saveMealTemplate",
)
async def save_meal_template(
    body: SaveMealTemplateRequest, user_sub: CurrentUser, session: DbSession
) -> MealTemplateSummaryOut:
    try:
        template = await service.save_meal_template(
            session,
            user_sub,
            name=body.name,
            log_ids=body.log_ids,
            default_meal_type=body.default_meal_type,
            template_id=body.template_id,
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MealTemplateSummaryOut.model_validate(template)


@router.patch(
    "/templates/{template_id}/items/{item_id}",
    response_model=MealTemplateSummaryOut,
    operation_id="updateMealTemplateItem",
)
async def update_meal_template_item(
    template_id: uuid.UUID,
    item_id: uuid.UUID,
    body: UpdateMealTemplateItemRequest,
    user_sub: CurrentUser,
    session: DbSession,
) -> MealTemplateSummaryOut:
    try:
        template = await service.update_meal_template_item(
            session,
            user_sub,
            template_id=template_id,
            item_id=item_id,
            name=body.name,
            serving_description=body.serving_description,
            values=body.values,
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MealTemplateSummaryOut.model_validate(template)


@router.delete("/templates/{template_id}", status_code=204, operation_id="deleteMealTemplate")
async def delete_meal_template(
    template_id: uuid.UUID, user_sub: CurrentUser, session: DbSession
) -> None:
    try:
        await service.delete_meal_template(session, user_sub, template_id)
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/templates/{template_id}/log",
    response_model=list[LogOut],
    status_code=201,
    operation_id="logMealTemplate",
)
async def log_meal_template(
    template_id: uuid.UUID, body: LogMealTemplateRequest, user_sub: CurrentUser, session: DbSession
) -> list[LogOut]:
    try:
        logs = await service.log_meal_template(
            session,
            user_sub,
            template_id=template_id,
            multiplier=body.multiplier,
            meal_type=body.meal_type,
            logged_at=body.logged_at,
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [LogOut.model_validate(log) for log in logs]


@router.get("/goals", response_model=list[GoalOut], operation_id="getGoals")
async def get_goals(user_sub: CurrentUser, session: DbSession) -> list[GoalOut]:
    goals = await service.get_goals(session, user_sub)
    return [GoalOut.model_validate(g) for g in goals]


@router.put("/goals", response_model=list[GoalOut], operation_id="setGoals")
async def set_goals(
    body: SetGoalsRequest, user_sub: CurrentUser, session: DbSession
) -> list[GoalOut]:
    try:
        goals = await service.set_goals(
            session, user_sub, goals=[g.model_dump() for g in body.goals]
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [GoalOut.model_validate(g) for g in goals]
