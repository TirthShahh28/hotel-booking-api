from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.booking import Booking, BookingStatus, Guest
from app.models.hotel import Room
from app.services.inventory import (
    iter_nights,
    lock_inventory_rows,
    restore_inventory,
)
from app.services.pricing import PricingContext, PricingEngine, default_engine

# Explicit state machine. Any transition not listed is illegal — interviewers love this.
ALLOWED_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.RESERVED: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {BookingStatus.CANCELLED},
    BookingStatus.CANCELLED: set(),
}


class BookingError(Exception):
    pass


class InvalidTransition(BookingError):
    pass


def assert_transition(current: BookingStatus, target: BookingStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"cannot transition {current.value} -> {target.value}")


async def init_booking(
    db: AsyncSession,
    user_id: int,
    room_id: int,
    check_in: date,
    check_out: date,
    engine: PricingEngine | None = None,
) -> Booking:
    """Acquire inventory locks, decrement, and create a RESERVED booking.

    Pricing is computed from the current inventory snapshot (pre-decrement) so
    the customer pays the rate that matches the market state when they booked.
    """
    room = await db.get(Room, room_id)
    if room is None:
        raise BookingError("room not found")

    # Single lock acquisition: pricing sees the pre-decrement snapshot, then we decrement
    # the same rows under the same lock. No double-lock, no race between price and decrement.
    nights = iter_nights(check_in, check_out)
    inventory_rows = await lock_inventory_rows(db, room_id=room_id, nights=nights)

    engine = engine or default_engine()
    total = engine.compute(
        PricingContext(
            base_price_cents=room.base_price_cents,
            check_in=check_in,
            check_out=check_out,
            inventory_rows=inventory_rows,
        )
    )

    if any(row.available_units <= 0 for row in inventory_rows):
        raise BookingError("room is sold out for one or more nights in the requested range")
    for row in inventory_rows:
        row.available_units -= 1

    booking = Booking(
        user_id=user_id,
        room_id=room_id,
        check_in=check_in,
        check_out=check_out,
        status=BookingStatus.RESERVED,
        total_price_cents=total,
    )
    db.add(booking)
    await db.flush()
    return booking


async def attach_guest(
    db: AsyncSession,
    booking: Booking,
    first_name: str,
    last_name: str,
    phone: str | None,
    email: str | None,
) -> Guest:
    if booking.status != BookingStatus.RESERVED:
        raise BookingError("guests can only be attached while the booking is RESERVED")
    guest = Guest(
        user_id=booking.user_id,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
    )
    db.add(guest)
    await db.flush()
    booking.guests.append(guest)
    await db.flush()
    return guest


async def cancel_booking(db: AsyncSession, booking: Booking) -> Booking:
    assert_transition(booking.status, BookingStatus.CANCELLED)
    await restore_inventory(
        db, room_id=booking.room_id, check_in=booking.check_in, check_out=booking.check_out
    )
    booking.status = BookingStatus.CANCELLED
    await db.flush()
    return booking


async def confirm_booking(db: AsyncSession, booking: Booking) -> Booking:
    assert_transition(booking.status, BookingStatus.CONFIRMED)
    booking.status = BookingStatus.CONFIRMED
    await db.flush()
    return booking


async def reap_expired_reservations(db: AsyncSession) -> int:
    """Release RESERVED bookings older than the hold window. Returns count reaped."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.reservation_hold_minutes)
    stmt = select(Booking).where(
        Booking.status == BookingStatus.RESERVED,
        Booking.created_at < cutoff,
    )
    expired = (await db.scalars(stmt)).all()
    for booking in expired:
        await cancel_booking(db, booking)
    return len(expired)
