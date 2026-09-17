from pydantic import BaseModel, ConfigDict, Field


class PushSubscriptionIn(BaseModel):
    """Exactly the shape `PushSubscription.toJSON()` produces in the browser, so the SPA
    can post what the Push API handed it without reshaping."""

    endpoint: str
    keys: dict[str, str]


class SetReminderRequest(BaseModel):
    enabled: bool
    # Local hour. Omitted when enabling means the default; ignored when disabling.
    hour: int | None = Field(default=None, ge=0, le=23)


class ReminderSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    hour: int | None
    subscribed_devices: int


class PushConfigOut(BaseModel):
    """What the SPA needs before it can subscribe. `public_key` is null when push isn't
    configured, which is the signal to hide the toggle rather than offer something that
    can only fail."""

    enabled: bool
    public_key: str | None
