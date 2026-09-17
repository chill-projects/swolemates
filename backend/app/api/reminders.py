from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.schemas.reminders import (
    PushConfigOut,
    PushSubscriptionIn,
    ReminderSettingsOut,
    SetReminderRequest,
)
from app.services import reminders as service

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("/config", response_model=PushConfigOut, operation_id="getPushConfig")
async def get_push_config() -> PushConfigOut:
    """Unauthenticated: it carries no user data, only whether this deployment can send
    push at all and the public half of the VAPID pair, which the browser needs to
    subscribe and which is public by design."""
    settings = get_settings()
    return PushConfigOut(
        enabled=settings.push_enabled,
        public_key=settings.vapid_public_key or None,
    )


@router.get("", response_model=ReminderSettingsOut, operation_id="getReminderSettings")
async def get_reminder_settings(user_sub: CurrentUser, session: DbSession) -> ReminderSettingsOut:
    return ReminderSettingsOut.model_validate(await service.get_settings_for(session, user_sub))


@router.put("", response_model=ReminderSettingsOut, operation_id="setReminderSettings")
async def set_reminder_settings(
    body: SetReminderRequest, user_sub: CurrentUser, session: DbSession
) -> ReminderSettingsOut:
    try:
        settings = await service.set_reminder(
            session, user_sub, enabled=body.enabled, hour=body.hour
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ReminderSettingsOut.model_validate(settings)


@router.post("/subscriptions", status_code=204, operation_id="addPushSubscription")
async def add_push_subscription(
    body: PushSubscriptionIn, user_sub: CurrentUser, session: DbSession
) -> None:
    if not get_settings().push_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications aren't configured on this server.",
        )
    p256dh, auth = body.keys.get("p256dh"), body.keys.get("auth")
    if not p256dh or not auth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is missing its encryption keys.",
        )
    await service.subscribe(session, user_sub, endpoint=body.endpoint, p256dh=p256dh, auth=auth)


@router.api_route(
    "/subscriptions", methods=["DELETE"], status_code=204, operation_id="removePushSubscription"
)
async def remove_push_subscription(
    body: PushSubscriptionIn, user_sub: CurrentUser, session: DbSession
) -> None:
    await service.unsubscribe(session, user_sub, endpoint=body.endpoint)
