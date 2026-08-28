"""Per-user timezone helpers (#19-adjacent, now resolved).

Every instant in the DB is stored UTC-aware (see `db.py`'s `-c timezone=utc`). What
varies per user is only *which calendar day* an instant falls on and *when "today"
starts* — so all the day-boundary logic funnels through here, taking an IANA
`ZoneInfo` (e.g. `America/Los_Angeles`, which tracks the PST/PDT switch itself — never
a fixed offset, which is wrong half the year).

Resolution order for a request lives in `deps.resolve_user_timezone`: a valid
`X-Timezone` header (the live browser zone) → the stored `user_profiles.timezone` →
UTC. Service functions that aren't request-scoped (MCP tools, partner summaries) fall
back to the stored value via `profile.get_user_timezone`.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC_ZONE = ZoneInfo("UTC")


def resolve_timezone(name: str | None) -> ZoneInfo:
    """Best-effort: an unknown or malformed name falls back to UTC rather than raising.
    Used on the read path, where a bad stored/header value must never 500 a request."""
    if not name:
        return UTC_ZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC_ZONE


def validate_timezone_name(name: str) -> str:
    """Strict: raises `ValueError` on anything `ZoneInfo` can't load. Used on the write
    path (settings form, `update_profile` MCP tool) so a typo comes back as a 400 /
    friendly tool reply instead of being silently stored and coerced to UTC later."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"{name!r} is not a valid IANA timezone name") from exc
    return name


def local_date(instant: datetime, tz: ZoneInfo) -> date:
    """The calendar date `instant` falls on in `tz`. A naive `instant` is treated as
    UTC (what Postgres does with a naive value in a `timestamptz` column here)."""
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(tz).date()


def parse_local_datetime(text: str, tz: ZoneInfo) -> datetime:
    """Parse an ISO string a user/model supplied for backdating, resolved in `tz`:

    - a date only (`2026-08-26`) → local noon that day (noon, not midnight, so a DST
      transition can't bump it to the previous/next day)
    - a naive datetime (`2026-08-26T19:30`) → that wall-clock time in `tz`
    - an aware datetime (`...+02:00`, `...Z`) → kept as given

    Returns a tz-aware instant, ready to store.
    """
    parsed = datetime.fromisoformat(text)
    if len(text) <= 10:  # date only
        parsed = parsed.replace(hour=12)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def today_in(tz: ZoneInfo) -> date:
    """The current calendar date in `tz` — the per-user replacement for `date.today()`
    (server-local, i.e. UTC on Railway) and `datetime.now(UTC).date()`."""
    return datetime.now(tz).date()


def local_day_bounds_utc(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """The UTC-aware instant range `[start, end)` covering the local calendar `day` in
    `tz` — half-open, so callers filter `>= start` and `< end`. Query the DB with
    these; bucket a row back to its local day with `row.astimezone(tz).date()`."""
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return start, end
