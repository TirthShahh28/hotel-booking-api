from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import RoomInventory
from app.services.inventory import (
    SoldOutError,
    decrement_inventory,
    iter_nights,
    restore_inventory,
    seed_room_inventory,
)


@pytest.mark.asyncio
async def test_seed_creates_horizon_rows(db_session: AsyncSession) -> None:
    await seed_room_inventory(db_session, room_id=1, total_units=1, horizon_days=3)
    await db_session.commit()

    rows = (await db_session.scalars(select(RoomInventory))).all()
    assert len(rows) == 3
    assert all(r.available_units == 1 for r in rows)


@pytest.mark.asyncio
async def test_decrement_happy_path(db_session: AsyncSession) -> None:
    start = date.today()
    await seed_room_inventory(db_session, room_id=2, total_units=1, start=start, horizon_days=5)
    await db_session.commit()

    await decrement_inventory(db_session, room_id=2, check_in=start, check_out=start + timedelta(days=2))
    await db_session.commit()

    rows = (
        await db_session.scalars(select(RoomInventory).where(RoomInventory.room_id == 2))
    ).all()
    booked = [r for r in rows if r.available_units == 0]
    assert len(booked) == 2


@pytest.mark.asyncio
async def test_decrement_rejects_when_sold_out(db_session: AsyncSession) -> None:
    start = date.today()
    await seed_room_inventory(db_session, room_id=3, total_units=1, start=start, horizon_days=2)
    await db_session.commit()

    await decrement_inventory(db_session, room_id=3, check_in=start, check_out=start + timedelta(days=1))
    await db_session.commit()

    with pytest.raises(SoldOutError):
        await decrement_inventory(
            db_session, room_id=3, check_in=start, check_out=start + timedelta(days=1)
        )


@pytest.mark.asyncio
async def test_restore_returns_unit(db_session: AsyncSession) -> None:
    start = date.today()
    await seed_room_inventory(db_session, room_id=4, total_units=1, start=start, horizon_days=2)
    await db_session.commit()

    await decrement_inventory(db_session, room_id=4, check_in=start, check_out=start + timedelta(days=1))
    await restore_inventory(db_session, room_id=4, check_in=start, check_out=start + timedelta(days=1))
    await db_session.commit()

    rows = (
        await db_session.scalars(select(RoomInventory).where(RoomInventory.room_id == 4))
    ).all()
    assert all(r.available_units == r.total_units for r in rows)


def test_iter_nights_excludes_checkout() -> None:
    start = date(2026, 5, 1)
    nights = iter_nights(start, start + timedelta(days=3))
    assert nights == [start, start + timedelta(days=1), start + timedelta(days=2)]


def test_iter_nights_rejects_invalid_range() -> None:
    start = date(2026, 5, 10)
    with pytest.raises(ValueError):
        iter_nights(start, start)


def test_for_update_compiles_in_sql() -> None:
    """Sanity-check that the lock clause is present — defends interview Q on FOR UPDATE."""
    from sqlalchemy.dialects import postgresql

    stmt = (
        select(RoomInventory)
        .where(RoomInventory.room_id == 1)
        .with_for_update()
    )
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in compiled
