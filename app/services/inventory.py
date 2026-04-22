from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import RoomInventory

SEED_HORIZON_DAYS = 365


async def seed_room_inventory(
    db: AsyncSession,
    room_id: int,
    total_units: int,
    start: date | None = None,
    horizon_days: int = SEED_HORIZON_DAYS,
) -> None:
    """Seed per-day inventory rows for a room over the next N days."""
    start = start or date.today()
    rows = [
        RoomInventory(
            room_id=room_id,
            date=start + timedelta(days=i),
            total_units=total_units,
            available_units=total_units,
        )
        for i in range(horizon_days)
    ]
    db.add_all(rows)
    await db.flush()


def iter_nights(check_in: date, check_out: date) -> list[date]:
    """Nights billed for a stay: [check_in, check_out). A 2-night stay = 2 rows."""
    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")
    return [check_in + timedelta(days=i) for i in range((check_out - check_in).days)]


async def lock_inventory_rows(
    db: AsyncSession,
    room_id: int,
    nights: Sequence[date],
) -> list[RoomInventory]:
    """Acquire row-level locks via SELECT ... FOR UPDATE for every night of the stay.

    Postgres blocks concurrent transactions here; the loser waits, then sees the
    decremented value. SQLite ignores the lock but still serializes via its writer
    lock, so the invariant holds in tests.
    """
    stmt = (
        select(RoomInventory)
        .where(RoomInventory.room_id == room_id, RoomInventory.date.in_(list(nights)))
        .order_by(RoomInventory.date)
        .with_for_update()
    )
    result = await db.scalars(stmt)
    rows = list(result.all())
    if len(rows) != len(nights):
        raise InventoryError("inventory not seeded for requested dates")
    return rows


async def decrement_inventory(
    db: AsyncSession,
    room_id: int,
    check_in: date,
    check_out: date,
) -> list[RoomInventory]:
    """Lock + decrement every night of the stay. Raises SoldOutError if any night is 0."""
    nights = iter_nights(check_in, check_out)
    rows = await lock_inventory_rows(db, room_id, nights)
    if any(r.available_units <= 0 for r in rows):
        raise SoldOutError("room is sold out for one or more nights in the requested range")
    for row in rows:
        row.available_units -= 1
    return rows


async def restore_inventory(
    db: AsyncSession,
    room_id: int,
    check_in: date,
    check_out: date,
) -> None:
    nights = iter_nights(check_in, check_out)
    rows = await lock_inventory_rows(db, room_id, nights)
    for row in rows:
        if row.available_units < row.total_units:
            row.available_units += 1


class InventoryError(Exception):
    pass


class SoldOutError(InventoryError):
    pass
