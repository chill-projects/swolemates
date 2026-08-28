from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.timezones import (
    local_date,
    local_day_bounds_utc,
    parse_local_datetime,
    resolve_timezone,
    today_in,
    validate_timezone_name,
)


@pytest.mark.parametrize("bad", [None, "", "Not/AZone", "PST", "-08:00", "Etc/Nonsense"])
def test_resolve_timezone_falls_back_to_utc(bad: str | None) -> None:
    assert resolve_timezone(bad).key == "UTC"


def test_resolve_timezone_keeps_a_valid_iana_name() -> None:
    assert resolve_timezone("America/Los_Angeles").key == "America/Los_Angeles"


def test_validate_timezone_name_rejects_offsets_and_abbreviations() -> None:
    for bad in ("PST", "-08:00", "America/Nowhere"):
        with pytest.raises(ValueError):
            validate_timezone_name(bad)
    assert validate_timezone_name("Europe/London") == "Europe/London"


def test_local_day_bounds_are_half_open_and_dst_aware() -> None:
    la = ZoneInfo("America/Los_Angeles")
    # 2026-08-25 is PDT (UTC-7): local midnight is 07:00Z, next midnight 07:00Z +1d.
    start, end = local_day_bounds_utc(date(2026, 8, 25), la)
    assert start == datetime(2026, 8, 25, 7, tzinfo=UTC)
    assert end == datetime(2026, 8, 26, 7, tzinfo=UTC)


def test_local_date_treats_naive_as_utc() -> None:
    la = ZoneInfo("America/Los_Angeles")
    # 03:00Z on the 26th is still 20:00 on the 25th in LA.
    assert local_date(datetime(2026, 8, 26, 3, 0), la) == date(2026, 8, 25)
    assert local_date(datetime(2026, 8, 26, 3, 0, tzinfo=UTC), la) == date(2026, 8, 25)


def test_today_in_matches_utc_when_zone_is_utc() -> None:
    assert today_in(ZoneInfo("UTC")) == datetime.now(UTC).date()


class TestParseLocalDatetime:
    la = ZoneInfo("America/Los_Angeles")

    def test_bare_date_becomes_local_noon(self) -> None:
        parsed = parse_local_datetime("2026-08-26", self.la)
        assert parsed.tzinfo is not None
        assert parsed.hour == 12
        assert local_date(parsed, self.la) == date(2026, 8, 26)
        # …and lands on the same UTC calendar day here — the whole point vs. naive UTC
        assert local_date(parsed, ZoneInfo("UTC")) == date(2026, 8, 26)

    def test_naive_datetime_is_wall_clock_in_zone(self) -> None:
        parsed = parse_local_datetime("2026-08-26T19:30", self.la)
        assert parsed.utcoffset() == datetime(2026, 8, 26, 19, 30, tzinfo=self.la).utcoffset()
        assert local_date(parsed, self.la) == date(2026, 8, 26)

    def test_aware_datetime_is_left_alone(self) -> None:
        parsed = parse_local_datetime("2026-08-26T19:30:00+02:00", self.la)
        assert parsed == datetime.fromisoformat("2026-08-26T19:30:00+02:00")
