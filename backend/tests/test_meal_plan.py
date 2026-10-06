"""Meal plan service — the Plan tab's eating half.

Written before the implementation. What these tests pin down, in order of how much
they'd hurt to get wrong:

  * a slot holds exactly one meal, and planning into a full slot replaces it;
  * macros are *derived* from whatever the meal came from, except when the caller
    has overridden them, and an entry whose numbers nobody knows says so rather
    than counting as zero;
  * every read and write is scoped to the caller.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import meal_plan as service
from app.services import nutrition as nutrition_service
from app.services import profile as profile_service
from app.services.errors import NotFoundError
from tests.conftest import OTHER_USER, TEST_USER

MON = date(2026, 9, 28)
TUE = date(2026, 9, 29)
WED = date(2026, 9, 30)


async def _template(
    session: AsyncSession,
    user: str,
    name: str,
    *,
    calories: str = "600",
    protein: str = "40",
) -> nutrition_service.MealTemplateSummary:
    """A saved meal, built the only way the app allows: from a logged entry."""
    log = await nutrition_service.log_nutrition(
        session,
        user,
        entries=[
            {"trackable_key": "calories", "value": Decimal(calories)},
            {"trackable_key": "protein_g", "value": Decimal(protein)},
        ],
        name=name,
    )
    return await nutrition_service.save_meal_template(session, user, name=name, log_ids=[log.id])


# --------------------------------------------------------------------------- slots


async def test_plan_meal_puts_a_saved_meal_in_a_slot(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Chicken and rice")

    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="lunch", template_id=template.id
    )

    assert planned.name == "Chicken and rice"
    assert planned.source == "template"
    assert planned.meal_type == "lunch"
    assert planned.scheduled_for == MON
    assert planned.status == "planned"


async def test_a_slot_holds_one_meal_so_planning_again_replaces_it(
    session: AsyncSession,
) -> None:
    first = await _template(session, TEST_USER, "Chicken and rice")
    second = await _template(session, TEST_USER, "Salmon poke bowl")

    await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="lunch", template_id=first.id
    )
    await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="lunch", template_id=second.id
    )

    day = (await service.get_meal_plan(session, TEST_USER, start=MON, end=MON))[0]
    assert [m.name for m in day.meals] == ["Salmon poke bowl"]


async def test_different_slots_on_a_day_coexist(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Usual breakfast")
    for meal_type in ("breakfast", "lunch", "dinner", "snack"):
        await service.plan_meal(
            session,
            TEST_USER,
            scheduled_for=MON,
            meal_type=meal_type,
            template_id=template.id,
        )

    day = (await service.get_meal_plan(session, TEST_USER, start=MON, end=MON))[0]
    assert [m.meal_type for m in day.meals] == ["breakfast", "lunch", "dinner", "snack"]


async def test_plan_meal_rejects_an_unknown_meal_type(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Anything")
    with pytest.raises(ValueError, match="meal type"):
        await service.plan_meal(
            session, TEST_USER, scheduled_for=MON, meal_type="brunch", template_id=template.id
        )


async def test_plan_meal_404s_for_someone_elses_template(session: AsyncSession) -> None:
    theirs = await _template(session, OTHER_USER, "Theirs")
    with pytest.raises(NotFoundError):
        await service.plan_meal(
            session, TEST_USER, scheduled_for=MON, meal_type="lunch", template_id=theirs.id
        )


# ------------------------------------------------------------------------- macros


async def test_macros_come_from_the_saved_meal(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Steak", calories="720", protein="55")

    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )

    assert planned.values["calories"] == Decimal("720")
    assert planned.values["protein_g"] == Decimal("55")
    assert planned.estimated is True
    assert planned.overridden is False


async def test_a_portion_scales_the_macros(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Curry", calories="800", protein="50")

    planned = await service.plan_meal(
        session,
        TEST_USER,
        scheduled_for=MON,
        meal_type="dinner",
        template_id=template.id,
        portion=Decimal("0.5"),
    )

    assert planned.values["calories"] == Decimal("400")
    assert planned.values["protein_g"] == Decimal("25")


async def test_an_ad_hoc_meal_with_no_numbers_is_honestly_unknown(
    session: AsyncSession,
) -> None:
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", name="Dinner at Mum's"
    )

    assert planned.name == "Dinner at Mum's"
    assert planned.source == "adhoc"
    assert planned.values == {}
    assert planned.estimated is False


async def test_an_unknown_meal_does_not_count_as_zero_in_the_day_total(
    session: AsyncSession,
) -> None:
    template = await _template(session, TEST_USER, "Breakfast", calories="360", protein="18")
    await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="breakfast", template_id=template.id
    )
    await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", name="Dinner at Mum's"
    )

    day = (await service.get_meal_plan(session, TEST_USER, start=MON, end=MON))[0]
    assert day.totals["calories"] == Decimal("360")
    assert day.unestimated == 1


async def test_ad_hoc_macros_can_be_given_at_plan_time(session: AsyncSession) -> None:
    planned = await service.plan_meal(
        session,
        TEST_USER,
        scheduled_for=MON,
        meal_type="dinner",
        name="Takeaway",
        values={"calories": Decimal("900"), "protein_g": Decimal("45")},
    )

    assert planned.values["calories"] == Decimal("900")
    assert planned.estimated is True


# -------------------------------------------------------------------------- edits


async def test_macros_can_be_overridden(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Steak", calories="720", protein="55")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )

    edited = await service.update_planned_meal(
        session,
        TEST_USER,
        planned_meal_id=planned.id,
        values={"calories": Decimal("650"), "protein_g": Decimal("60")},
    )

    assert edited.values["calories"] == Decimal("650")
    assert edited.overridden is True
    assert edited.template_id == template.id  # still knows where it came from


async def test_an_override_survives_the_saved_meal_changing(session: AsyncSession) -> None:
    """The whole point of storing the override: a plan the caller has corrected by hand
    must not be silently rewritten when the underlying saved meal is edited later."""
    template = await _template(session, TEST_USER, "Steak", calories="720", protein="55")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )
    await service.update_planned_meal(
        session, TEST_USER, planned_meal_id=planned.id, values={"calories": Decimal("650")}
    )

    item = template.items[0]
    await nutrition_service.update_meal_template_item(
        session,
        TEST_USER,
        template_id=template.id,
        item_id=item.id,
        name=item.name,
        serving_description=item.serving_description,
        values={"calories": Decimal("999")},
    )

    day = (await service.get_meal_plan(session, TEST_USER, start=MON, end=MON))[0]
    assert day.meals[0].values["calories"] == Decimal("650")


async def test_clearing_an_override_falls_back_to_the_saved_meal(
    session: AsyncSession,
) -> None:
    template = await _template(session, TEST_USER, "Steak", calories="720", protein="55")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )
    await service.update_planned_meal(
        session, TEST_USER, planned_meal_id=planned.id, values={"calories": Decimal("650")}
    )

    restored = await service.update_planned_meal(
        session, TEST_USER, planned_meal_id=planned.id, values={}
    )

    assert restored.overridden is False
    assert restored.values["calories"] == Decimal("720")


async def test_a_planned_meal_can_be_renamed(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Steak")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )

    edited = await service.update_planned_meal(
        session, TEST_USER, planned_meal_id=planned.id, name="Steak, smaller"
    )
    assert edited.name == "Steak, smaller"


async def test_a_planned_meal_can_move_to_another_day_or_slot(
    session: AsyncSession,
) -> None:
    template = await _template(session, TEST_USER, "Steak")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )

    moved = await service.update_planned_meal(
        session, TEST_USER, planned_meal_id=planned.id, scheduled_for=WED, meal_type="lunch"
    )

    assert moved.scheduled_for == WED
    assert moved.meal_type == "lunch"
    days = await service.get_meal_plan(session, TEST_USER, start=MON, end=WED)
    assert [len(d.meals) for d in days] == [0, 0, 1]


async def test_moving_onto_an_occupied_slot_replaces_what_was_there(
    session: AsyncSession,
) -> None:
    steak = await _template(session, TEST_USER, "Steak")
    soup = await _template(session, TEST_USER, "Soup")
    keeper = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=steak.id
    )
    await service.plan_meal(
        session, TEST_USER, scheduled_for=TUE, meal_type="dinner", template_id=soup.id
    )

    await service.update_planned_meal(
        session, TEST_USER, planned_meal_id=keeper.id, scheduled_for=TUE
    )

    days = await service.get_meal_plan(session, TEST_USER, start=MON, end=TUE)
    assert [m.name for d in days for m in d.meals] == ["Steak"]


async def test_clear_planned_meal_empties_the_slot(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Steak")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )

    await service.clear_planned_meal(session, TEST_USER, planned_meal_id=planned.id)

    day = (await service.get_meal_plan(session, TEST_USER, start=MON, end=MON))[0]
    assert day.meals == []


@pytest.mark.parametrize("op", ["update", "clear"])
async def test_edits_are_scoped_to_the_caller(session: AsyncSession, op: str) -> None:
    template = await _template(session, OTHER_USER, "Theirs")
    theirs = await service.plan_meal(
        session, OTHER_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )

    with pytest.raises(NotFoundError):
        if op == "update":
            await service.update_planned_meal(
                session, TEST_USER, planned_meal_id=theirs.id, name="mine now"
            )
        else:
            await service.clear_planned_meal(session, TEST_USER, planned_meal_id=theirs.id)


# ------------------------------------------------------------------------ reading


async def test_get_meal_plan_returns_every_day_in_range_even_empty_ones(
    session: AsyncSession,
) -> None:
    days = await service.get_meal_plan(session, TEST_USER, start=MON, end=WED)
    assert [d.scheduled_for for d in days] == [MON, TUE, WED]
    assert all(d.meals == [] for d in days)


async def test_get_meal_plan_does_not_leak_another_users_plan(
    session: AsyncSession,
) -> None:
    template = await _template(session, OTHER_USER, "Theirs")
    await service.plan_meal(
        session, OTHER_USER, scheduled_for=MON, meal_type="lunch", template_id=template.id
    )

    days = await service.get_meal_plan(session, TEST_USER, start=MON, end=MON)
    assert days[0].meals == []


async def test_meals_come_back_in_slot_order_not_insertion_order(
    session: AsyncSession,
) -> None:
    template = await _template(session, TEST_USER, "Anything")
    for meal_type in ("snack", "breakfast", "dinner", "lunch"):
        await service.plan_meal(
            session,
            TEST_USER,
            scheduled_for=MON,
            meal_type=meal_type,
            template_id=template.id,
        )

    day = (await service.get_meal_plan(session, TEST_USER, start=MON, end=MON))[0]
    assert [m.meal_type for m in day.meals] == ["breakfast", "lunch", "dinner", "snack"]


# ----------------------------------------------------------------------- the tray


async def test_a_leftover_carries_its_own_macros(session: AsyncSession) -> None:
    item = await service.add_kitchen_item(
        session,
        TEST_USER,
        kind="leftover",
        name="Chicken curry",
        portion=Decimal("0.5"),
        values={"calories": Decimal("780"), "protein_g": Decimal("48")},
    )

    assert item.kind == "leftover"
    assert item.values["calories"] == Decimal("390")  # already scaled by the portion


async def test_a_leftover_can_be_planned_straight_into_a_slot(
    session: AsyncSession,
) -> None:
    item = await service.add_kitchen_item(
        session,
        TEST_USER,
        kind="leftover",
        name="Chicken curry",
        portion=Decimal("0.5"),
        values={"calories": Decimal("780"), "protein_g": Decimal("48")},
    )

    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", kitchen_item_id=item.id
    )

    assert planned.source == "leftover"
    assert planned.name == "Chicken curry"
    assert planned.values["calories"] == Decimal("390")


async def test_an_ingredient_has_no_macros_and_points_at_meals_instead(
    session: AsyncSession,
) -> None:
    slaw = await _template(session, TEST_USER, "Cabbage slaw")
    stirfry = await _template(session, TEST_USER, "Tofu stir-fry")

    item = await service.add_kitchen_item(
        session,
        TEST_USER,
        kind="ingredient",
        name="Half a cabbage",
        template_ids=[slaw.id, stirfry.id],
    )

    assert item.values == {}
    assert {t.name for t in item.templates} == {"Cabbage slaw", "Tofu stir-fry"}


async def test_an_ingredient_cannot_be_planned_directly(session: AsyncSession) -> None:
    item = await service.add_kitchen_item(
        session, TEST_USER, kind="ingredient", name="Half a cabbage"
    )

    with pytest.raises(ValueError, match="ingredient"):
        await service.plan_meal(
            session, TEST_USER, scheduled_for=MON, meal_type="dinner", kitchen_item_id=item.id
        )


async def test_kitchen_items_are_scoped_to_the_caller(session: AsyncSession) -> None:
    await service.add_kitchen_item(session, OTHER_USER, kind="ingredient", name="Theirs")
    assert await service.list_kitchen(session, TEST_USER) == []


async def test_a_kitchen_item_can_be_removed(session: AsyncSession) -> None:
    item = await service.add_kitchen_item(
        session, TEST_USER, kind="ingredient", name="Half a cabbage"
    )
    await service.remove_kitchen_item(session, TEST_USER, item_id=item.id)
    assert await service.list_kitchen(session, TEST_USER) == []


async def test_removing_a_leftover_leaves_the_plan_that_used_it_intact(
    session: AsyncSession,
) -> None:
    """Deleting the tray entry must not blank out a day you'd already planned; the
    planned meal keeps the name and numbers it was given."""
    item = await service.add_kitchen_item(
        session,
        TEST_USER,
        kind="leftover",
        name="Chicken curry",
        portion=Decimal("0.5"),
        values={"calories": Decimal("780")},
    )
    await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", kitchen_item_id=item.id
    )

    await service.remove_kitchen_item(session, TEST_USER, item_id=item.id)

    day = (await service.get_meal_plan(session, TEST_USER, start=MON, end=MON))[0]
    assert day.meals[0].name == "Chicken curry"
    assert day.meals[0].values["calories"] == Decimal("390")


async def test_deleting_a_saved_meal_leaves_the_plan_that_used_it_intact(
    session: AsyncSession,
) -> None:
    """The FK is SET NULL; the macros are frozen onto the plan first, so the day keeps
    its numbers — scaled by the plan's portion — instead of going unestimated."""
    template = await _template(session, TEST_USER, "Chicken and rice", calories="600")
    await service.plan_meal(
        session,
        TEST_USER,
        scheduled_for=MON,
        meal_type="lunch",
        template_id=template.id,
        portion=Decimal("0.5"),
    )
    overridden = await service.plan_meal(
        session, TEST_USER, scheduled_for=TUE, meal_type="lunch", template_id=template.id
    )
    await service.update_planned_meal(
        session, TEST_USER, planned_meal_id=overridden.id, values={"calories": Decimal("500")}
    )

    await nutrition_service.delete_meal_template(session, TEST_USER, template.id)
    await session.flush()

    mon, tue = await service.get_meal_plan(session, TEST_USER, start=MON, end=TUE)
    assert mon.meals[0].name == "Chicken and rice"
    assert mon.meals[0].template_id is None
    assert mon.meals[0].values == {"calories": Decimal("300"), "protein_g": Decimal("20")}
    assert mon.unestimated == 0
    # A plan that already carried its own numbers keeps exactly those.
    assert tue.meals[0].values == {"calories": Decimal("500")}


async def test_deleting_a_saved_meal_does_not_touch_another_users_plans(
    session: AsyncSession,
) -> None:
    mine = await _template(session, TEST_USER, "Mine")
    theirs = await _template(session, OTHER_USER, "Theirs")
    planned = await service.plan_meal(
        session, OTHER_USER, scheduled_for=MON, meal_type="lunch", template_id=theirs.id
    )

    await nutrition_service.delete_meal_template(session, TEST_USER, mine.id)

    day = (await service.get_meal_plan(session, OTHER_USER, start=MON, end=MON))[0]
    assert day.meals[0].id == planned.id
    assert day.meals[0].overridden is False


async def test_ingredient_meal_names_resolve_to_saved_meals(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Coleslaw")

    ids = await service.resolve_saved_meal_names(session, TEST_USER, [" coleslaw "])
    assert ids == [template.id]
    with pytest.raises(NotFoundError, match="Kimchi"):
        await service.resolve_saved_meal_names(session, TEST_USER, ["Kimchi"])


# ------------------------------------------------------------------------ logging


async def test_logging_a_planned_meal_writes_it_into_the_day(
    session: AsyncSession,
) -> None:
    template = await _template(session, TEST_USER, "Steak", calories="720", protein="55")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )

    logged = await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)

    assert logged.status == "logged"
    day = await nutrition_service.get_nutrition_day(session, TEST_USER, day=MON)
    assert any(entry.name == "Steak" for entry in day.logs)


async def test_logging_lands_on_the_planned_local_day_west_of_utc(
    session: AsyncSession,
) -> None:
    """Midnight UTC on Monday is Sunday afternoon in Los Angeles; the entry must land
    on the Monday that was planned, in the caller's own zone."""
    la = ZoneInfo("America/Los_Angeles")
    await profile_service.sync_timezone(session, TEST_USER, "America/Los_Angeles")
    template = await _template(session, TEST_USER, "Steak", calories="720", protein="55")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )

    await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)

    monday = await nutrition_service.get_nutrition_day(session, TEST_USER, day=MON, tz=la)
    sunday = await nutrition_service.get_nutrition_day(
        session, TEST_USER, day=date(2026, 9, 27), tz=la
    )
    assert any(e.name == "Steak" for e in monday.logs)
    assert not any(e.name == "Steak" for e in sunday.logs)


async def test_deleting_the_logged_entry_puts_the_plan_back_to_planned(
    session: AsyncSession,
) -> None:
    template = await _template(session, TEST_USER, "Steak")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )
    logged = await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)

    await nutrition_service.delete_nutrition_log(session, TEST_USER, logged.log_group_id)

    meal = (await service.get_meal_plan(session, TEST_USER, start=MON, end=MON))[0].meals[0]
    assert meal.status == "planned"
    assert meal.log_group_id is None
    # ...and it can be logged again.
    again = await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)
    assert again.status == "logged"


async def test_undoing_the_logged_entry_puts_the_plan_back_to_planned(
    session: AsyncSession,
) -> None:
    template = await _template(session, TEST_USER, "Steak")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )
    await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)

    await nutrition_service.amend_last_log(session, TEST_USER)

    meal = (await service.get_meal_plan(session, TEST_USER, start=MON, end=MON))[0].meals[0]
    assert meal.status == "planned"


async def test_a_plan_stranded_by_an_old_delete_repairs_itself_on_read(
    session: AsyncSession,
) -> None:
    """A plan left `logged` by a delete that skipped the unlink (an older build, or
    a raw delete) reads back as `planned` rather than claiming a missing entry."""
    from sqlalchemy import delete as sa_delete

    from app.models.nutrition import Log

    template = await _template(session, TEST_USER, "Steak")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )
    logged = await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)
    await session.execute(sa_delete(Log).where(Log.id == logged.log_group_id))
    await session.flush()

    meal = (await service.get_meal_plan(session, TEST_USER, start=MON, end=MON))[0].meals[0]
    assert meal.status == "planned"
    assert meal.log_group_id is None


async def test_a_logged_plan_cannot_be_moved(session: AsyncSession) -> None:
    """Its entry is stamped on the original day; moving the plan would leave the two
    disagreeing about when it was eaten."""
    template = await _template(session, TEST_USER, "Steak")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )
    await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)

    with pytest.raises(ValueError, match="already been logged"):
        await service.update_planned_meal(
            session, TEST_USER, planned_meal_id=planned.id, scheduled_for=TUE
        )
    # Editing in place is still fine.
    renamed = await service.update_planned_meal(
        session, TEST_USER, planned_meal_id=planned.id, name="Ribeye"
    )
    assert renamed.status == "logged"


async def test_logging_twice_is_refused(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Steak")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )
    await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)

    with pytest.raises(ValueError, match="already"):
        await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)


async def test_an_overridden_plan_logs_the_numbers_you_edited(
    session: AsyncSession,
) -> None:
    template = await _template(session, TEST_USER, "Steak", calories="720", protein="55")
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )
    await service.update_planned_meal(
        session, TEST_USER, planned_meal_id=planned.id, values={"calories": Decimal("650")}
    )

    await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)

    day = await nutrition_service.get_nutrition_day(session, TEST_USER, day=MON)
    entry = next(e for e in day.logs if e.name == "Steak")
    assert entry.values["calories"] == Decimal("650")


async def test_a_meal_with_no_numbers_cannot_be_logged(session: AsyncSession) -> None:
    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", name="Dinner at Mum's"
    )

    with pytest.raises(ValueError, match="no macros"):
        await service.log_planned_meal(session, TEST_USER, planned_meal_id=planned.id)


async def test_logging_is_scoped_to_the_caller(session: AsyncSession) -> None:
    template = await _template(session, OTHER_USER, "Theirs")
    theirs = await service.plan_meal(
        session, OTHER_USER, scheduled_for=MON, meal_type="dinner", template_id=template.id
    )
    with pytest.raises(NotFoundError):
        await service.log_planned_meal(session, TEST_USER, planned_meal_id=theirs.id)


async def test_unknown_ids_raise_not_found(session: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await service.update_planned_meal(session, TEST_USER, planned_meal_id=uuid4(), name="nope")


# ------------------------------------------------------- resolving a spoken name


async def test_resolve_prefers_a_leftover_over_a_saved_meal_of_the_same_name(
    session: AsyncSession,
) -> None:
    """Both can be called "Chicken curry". The one in the fridge is the one that needs
    eating, so that is what "plan the chicken curry" should mean."""
    template = await _template(session, TEST_USER, "Chicken curry")
    item = await service.add_kitchen_item(
        session,
        TEST_USER,
        kind="leftover",
        name="Chicken curry",
        portion=Decimal("0.5"),
        values={"calories": Decimal("780")},
    )

    ref = await service.resolve_meal_reference(session, TEST_USER, "Chicken curry")

    assert ref == {"kitchen_item_id": item.id}
    assert template.id  # the saved meal exists and was deliberately not chosen


async def test_resolve_matches_a_saved_meal_by_name(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Salmon poke bowl")
    ref = await service.resolve_meal_reference(session, TEST_USER, "salmon poke bowl")
    assert ref == {"template_id": template.id}


async def test_resolve_falls_back_to_a_partial_match(session: AsyncSession) -> None:
    template = await _template(session, TEST_USER, "Salmon poke bowl")
    ref = await service.resolve_meal_reference(session, TEST_USER, "poke")
    assert ref == {"template_id": template.id}


async def test_resolve_gives_back_an_ad_hoc_name_when_nothing_matches(
    session: AsyncSession,
) -> None:
    ref = await service.resolve_meal_reference(session, TEST_USER, "Dinner at Mum's")
    assert ref == {"name": "Dinner at Mum's"}


async def test_resolve_does_not_reach_into_another_users_meals(
    session: AsyncSession,
) -> None:
    await _template(session, OTHER_USER, "Salmon poke bowl")
    ref = await service.resolve_meal_reference(session, TEST_USER, "Salmon poke bowl")
    assert ref == {"name": "Salmon poke bowl"}


async def test_a_resolved_name_can_be_planned_straight_through(
    session: AsyncSession,
) -> None:
    await _template(session, TEST_USER, "Steak", calories="720", protein="55")
    ref = await service.resolve_meal_reference(session, TEST_USER, "steak")

    planned = await service.plan_meal(
        session, TEST_USER, scheduled_for=MON, meal_type="dinner", **ref
    )
    assert planned.name == "Steak"
    assert planned.values["calories"] == Decimal("720")
