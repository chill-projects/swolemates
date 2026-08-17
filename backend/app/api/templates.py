import uuid

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas.templates import (
    CreateWorkoutTemplateRequest,
    TemplateOut,
    UpdateWorkoutTemplateRequest,
)
from app.services import workout_templates as service

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post("", response_model=TemplateOut, status_code=201, operation_id="createWorkoutTemplate")
async def create_workout_template(
    body: CreateWorkoutTemplateRequest, user_sub: CurrentUser, session: DbSession
) -> TemplateOut:
    try:
        template = await service.create_workout_template(
            session,
            user_sub,
            name=body.name,
            exercises=[e.model_dump() for e in body.exercises],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TemplateOut.model_validate(template)


@router.get("", response_model=list[TemplateOut], operation_id="listWorkoutTemplates")
async def list_workout_templates(user_sub: CurrentUser, session: DbSession) -> list[TemplateOut]:
    templates = await service.list_workout_templates(session, user_sub)
    return [TemplateOut.model_validate(t) for t in templates]


@router.get("/{template_id}", response_model=TemplateOut, operation_id="getWorkoutTemplate")
async def get_workout_template(
    template_id: uuid.UUID, user_sub: CurrentUser, session: DbSession
) -> TemplateOut:
    try:
        template = await service.get_workout_template(session, user_sub, template_id)
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TemplateOut.model_validate(template)


@router.post(
    "/{template_id}/entries", response_model=TemplateOut, operation_id="updateWorkoutTemplate"
)
async def update_workout_template(
    template_id: uuid.UUID,
    body: UpdateWorkoutTemplateRequest,
    user_sub: CurrentUser,
    session: DbSession,
) -> TemplateOut:
    try:
        template = await service.update_workout_template(
            session,
            user_sub,
            template_id=template_id,
            action=body.action,
            name=body.name,
            exercise=body.exercise,
            template_exercise_id=body.template_exercise_id,
            superset_with=body.superset_with,
            order=body.order,
            sets=body.sets,
            reps=body.reps,
            seconds=body.seconds,
            weight=body.weight,
            notes=body.notes,
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TemplateOut.model_validate(template)


@router.post("/{template_id}/archive", response_model=None, operation_id="archiveWorkoutTemplate")
async def archive_workout_template(
    template_id: uuid.UUID, user_sub: CurrentUser, session: DbSession
) -> None:
    try:
        await service.archive_workout_template(session, user_sub, template_id)
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
