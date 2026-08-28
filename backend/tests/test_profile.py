from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import WeightUnit
from app.services import profile as service
from tests.conftest import OTHER_USER, TEST_USER


async def test_get_profile_creates_defaults_on_first_call(client: AsyncClient) -> None:
    resp = await client.get("/api/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["weight_unit"] == "lbs"
    assert body["coach_notes"] is None
    assert body["onboarding_completed_at"] is None


async def test_update_profile_sets_weight_unit_and_notes(client: AsyncClient) -> None:
    resp = await client.patch(
        "/api/profile", json={"weight_unit": "kg", "coach_notes": "bad left knee"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["weight_unit"] == "kg"
    assert body["coach_notes"] == "bad left knee"


async def test_update_profile_partial_update_leaves_other_field_untouched(
    client: AsyncClient,
) -> None:
    await client.patch("/api/profile", json={"coach_notes": "only dumbbells at home"})
    resp = await client.patch("/api/profile", json={"weight_unit": "kg"})

    body = resp.json()
    assert body["weight_unit"] == "kg"
    assert body["coach_notes"] == "only dumbbells at home"


async def test_complete_onboarding_sets_timestamp_once(client: AsyncClient) -> None:
    first = await client.post("/api/profile/complete-onboarding")
    assert first.status_code == 200
    first_timestamp = first.json()["onboarding_completed_at"]
    assert first_timestamp is not None

    second = await client.post("/api/profile/complete-onboarding")
    assert second.json()["onboarding_completed_at"] == first_timestamp


async def test_update_profile_sets_and_validates_timezone(client: AsyncClient) -> None:
    ok = await client.patch("/api/profile", json={"timezone": "America/Los_Angeles"})
    assert ok.status_code == 200
    assert ok.json()["timezone"] == "America/Los_Angeles"

    bad = await client.patch("/api/profile", json={"timezone": "PST"})
    assert bad.status_code == 400
    # the invalid write left the good value in place
    assert (await client.get("/api/profile")).json()["timezone"] == "America/Los_Angeles"


async def test_whoami_seeds_timezone_from_header_only_while_unset(client: AsyncClient) -> None:
    await client.get("/api/whoami", headers={"X-Timezone": "Europe/Berlin"})
    assert (await client.get("/api/profile")).json()["timezone"] == "Europe/Berlin"

    # a later, different header does not overwrite the user's stored value
    await client.get("/api/whoami", headers={"X-Timezone": "Asia/Tokyo"})
    assert (await client.get("/api/profile")).json()["timezone"] == "Europe/Berlin"

    # a garbage header is ignored, not stored
    await client.get("/api/whoami", headers={"X-Timezone": "Mars/Olympus"})
    assert (await client.get("/api/profile")).json()["timezone"] == "Europe/Berlin"


async def test_users_have_independent_profiles(session: AsyncSession) -> None:
    """The whole permission model, asserted directly against the service layer."""
    await service.update_profile(session, OTHER_USER, weight_unit=WeightUnit.kg)
    await session.flush()

    mine = await service.get_or_create_profile(session, TEST_USER)
    theirs = await service.get_or_create_profile(session, OTHER_USER)

    assert mine.weight_unit == WeightUnit.lbs
    assert theirs.weight_unit == WeightUnit.kg


async def test_get_or_create_profile_returns_same_row_on_second_call(
    session: AsyncSession,
) -> None:
    first = await service.get_or_create_profile(session, TEST_USER)
    second = await service.get_or_create_profile(session, TEST_USER)
    assert first.user_id == second.user_id == TEST_USER
