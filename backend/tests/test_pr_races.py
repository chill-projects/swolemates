"""Two requests recording a PR for the same (user, exercise, kind) at once — e.g. the
same lifter finishing on two devices. Unlike the rest of the suite these can't use the
rolled-back `session` fixture: a race needs two connections that each really commit,
so every row here is committed under a throwaway user and deleted afterwards.

Each test plays the interleaving from the SQL lesson on isolation: A records a PR and
holds its transaction open; B runs the same check concurrently (finishing or blocking,
depending on the code); then A commits, then B.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.profile import UserProfile
from app.models.workouts import (
    Exercise,
    PersonalRecord,
    PersonalRecordKind,
    SetType,
    Workout,
    WorkoutSet,
)
from app.services import celebrations, workouts


@pytest.fixture
async def maker(migrated_database: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_database, connect_args={"options": "-c timezone=utc"})
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def user(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[str]:
    sub = f"race_{uuid.uuid4().hex}"
    yield sub
    async with maker() as s:
        await s.execute(delete(PersonalRecord).where(PersonalRecord.user_id == sub))
        await s.execute(delete(Workout).where(Workout.user_id == sub))
        await s.execute(delete(Exercise).where(Exercise.created_by == sub))
        await s.execute(delete(UserProfile).where(UserProfile.user_id == sub))
        await s.commit()


async def _logged_set(
    maker: async_sessionmaker[AsyncSession], user: str, weight: int
) -> tuple[uuid.UUID, uuid.UUID]:
    """A committed set (the PR row's FK target) and its exercise's id. Logging it also
    records it as the starting PR."""
    async with maker() as s:
        result = await workouts.log_set(
            s, user, exercise=f"Race Press {user}", reps=1, weight=Decimal(weight)
        )
        await s.commit()
    exercise = result.workout.exercises[-1]
    return exercise.exercise_id, exercise.sets[-1].id


def _set(set_id: uuid.UUID, weight: int) -> WorkoutSet:
    return WorkoutSet(
        id=set_id,
        set_type=SetType.reps,
        is_warmup=False,
        actual_weight=Decimal(weight),
        actual_reps=1,
        completed_at=datetime.now(UTC),
    )


async def _race(
    maker: async_sessionmaker[AsyncSession],
    user: str,
    exercise_id: uuid.UUID,
    set_id: uuid.UUID,
    *,
    a: int,
    b: int,
) -> tuple[list, list]:
    async def record(s: AsyncSession, weight: int) -> list:
        return await celebrations.check_and_record_prs(
            s,
            user,
            exercise_id=exercise_id,
            exercise_name="Race Press",
            sets=[_set(set_id, weight)],
        )

    async with maker() as sa, maker() as sb:
        a_result = await record(sa, a)
        b_task = asyncio.create_task(record(sb, b))
        await asyncio.sleep(0.2)  # B either finishes or blocks on A's lock
        await sa.commit()
        b_result = await asyncio.wait_for(b_task, timeout=5)
        await sb.commit()
    return a_result, b_result


async def _stored_weight_pr(
    maker: async_sessionmaker[AsyncSession], user: str, exercise_id: uuid.UUID
) -> Decimal | None:
    async with maker() as s:
        return await s.scalar(
            select(PersonalRecord.value).where(
                PersonalRecord.user_id == user,
                PersonalRecord.exercise_id == exercise_id,
                PersonalRecord.kind == PersonalRecordKind.weight,
            )
        )


async def test_a_lower_concurrent_pr_does_not_overwrite_a_higher_one(maker, user) -> None:
    """The lesson's Figure 2: stored 100, A=110, B=105, both read before either
    commits. B must not write 105 over A's committed 110 — nor celebrate it."""
    exercise_id, set_id = await _logged_set(maker, user, 100)

    a_result, b_result = await _race(maker, user, exercise_id, set_id, a=110, b=105)

    assert {c.kind for c in a_result} == {"weight", "e1rm"}
    assert b_result == []
    assert await _stored_weight_pr(maker, user, exercise_id) == 110


async def test_concurrent_first_prs_keep_the_higher_without_an_error(maker, user) -> None:
    """The lesson's check-yourself #1: no record yet, so there's no row for FOR UPDATE
    to lock. Both requests see "none" and insert; the second must not 500 on the
    unique constraint, and the higher value must be what's kept."""
    exercise_id, set_id = await _logged_set(maker, user, 100)
    async with maker() as s:
        await s.execute(delete(PersonalRecord).where(PersonalRecord.user_id == user))
        await s.commit()

    a_result, b_result = await _race(maker, user, exercise_id, set_id, a=110, b=105)

    assert {c.kind for c in a_result} == {"weight", "e1rm"}
    assert b_result == []
    assert await _stored_weight_pr(maker, user, exercise_id) == 110
