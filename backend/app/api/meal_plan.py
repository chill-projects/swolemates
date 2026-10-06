"""Meal plan REST router — thin, like every other one here. All logic and every
permission check lives in `app.services.meal_plan`, so the MCP tools get the same
behaviour for free."""

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession, UserTimezone
from app.schemas.meal_plan import (
    AddKitchenItemRequest,
    KitchenItemOut,
    PlanMealRequest,
    PlannedDayOut,
    PlannedMealOut,
    UpdateKitchenItemRequest,
    UpdatePlannedMealRequest,
)
from app.services import meal_plan as service
from app.services.errors import NotFoundError

router = APIRouter(tags=["meal-plan"])


@router.get("/meal-plan", response_model=list[PlannedDayOut], operation_id="getMealPlan")
async def get_meal_plan(
    user_sub: CurrentUser,
    session: DbSession,
    start: date,
    end: date,
) -> list[PlannedDayOut]:
    try:
        days = await service.get_meal_plan(session, user_sub, start=start, end=end)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [PlannedDayOut.model_validate(d) for d in days]


@router.post("/meal-plan", response_model=PlannedMealOut, status_code=201, operation_id="planMeal")
async def plan_meal(
    body: PlanMealRequest, user_sub: CurrentUser, session: DbSession
) -> PlannedMealOut:
    try:
        planned = await service.plan_meal(
            session,
            user_sub,
            scheduled_for=body.scheduled_for,
            meal_type=body.meal_type,
            template_id=body.template_id,
            kitchen_item_id=body.kitchen_item_id,
            name=body.name,
            portion=body.portion,
            values=body.values,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlannedMealOut.model_validate(planned)


@router.patch(
    "/meal-plan/{planned_meal_id}",
    response_model=PlannedMealOut,
    operation_id="updatePlannedMeal",
)
async def update_planned_meal(
    planned_meal_id: uuid.UUID,
    body: UpdatePlannedMealRequest,
    user_sub: CurrentUser,
    session: DbSession,
) -> PlannedMealOut:
    try:
        planned = await service.update_planned_meal(
            session,
            user_sub,
            planned_meal_id=planned_meal_id,
            name=body.name,
            portion=body.portion,
            values=body.values,
            scheduled_for=body.scheduled_for,
            meal_type=body.meal_type,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlannedMealOut.model_validate(planned)


@router.delete("/meal-plan/{planned_meal_id}", status_code=204, operation_id="clearPlannedMeal")
async def clear_planned_meal(
    planned_meal_id: uuid.UUID, user_sub: CurrentUser, session: DbSession
) -> None:
    try:
        await service.clear_planned_meal(session, user_sub, planned_meal_id=planned_meal_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/meal-plan/{planned_meal_id}/log",
    response_model=PlannedMealOut,
    operation_id="logPlannedMeal",
)
async def log_planned_meal(
    planned_meal_id: uuid.UUID, user_sub: CurrentUser, session: DbSession, tz: UserTimezone
) -> PlannedMealOut:
    try:
        planned = await service.log_planned_meal(
            session, user_sub, planned_meal_id=planned_meal_id, tz=tz
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlannedMealOut.model_validate(planned)


@router.get("/kitchen", response_model=list[KitchenItemOut], operation_id="listKitchen")
async def list_kitchen(user_sub: CurrentUser, session: DbSession) -> list[KitchenItemOut]:
    items = await service.list_kitchen(session, user_sub)
    return [KitchenItemOut.model_validate(i) for i in items]


@router.post(
    "/kitchen", response_model=KitchenItemOut, status_code=201, operation_id="addKitchenItem"
)
async def add_kitchen_item(
    body: AddKitchenItemRequest, user_sub: CurrentUser, session: DbSession
) -> KitchenItemOut:
    try:
        item = await service.add_kitchen_item(
            session,
            user_sub,
            kind=body.kind,
            name=body.name,
            portion=body.portion,
            values=body.values,
            template_ids=body.template_ids,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return KitchenItemOut.model_validate(item)


@router.patch("/kitchen/{item_id}", response_model=KitchenItemOut, operation_id="updateKitchenItem")
async def update_kitchen_item(
    item_id: uuid.UUID,
    body: UpdateKitchenItemRequest,
    user_sub: CurrentUser,
    session: DbSession,
) -> KitchenItemOut:
    try:
        item = await service.update_kitchen_item(
            session, user_sub, item_id=item_id, name=body.name, portion=body.portion
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return KitchenItemOut.model_validate(item)


@router.delete("/kitchen/{item_id}", status_code=204, operation_id="removeKitchenItem")
async def remove_kitchen_item(
    item_id: uuid.UUID, user_sub: CurrentUser, session: DbSession
) -> None:
    try:
        await service.remove_kitchen_item(session, user_sub, item_id=item_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
