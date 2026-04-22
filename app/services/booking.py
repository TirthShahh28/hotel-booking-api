from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.booking import Booking, BookingStatus, Guest
from app.models.hotel import Room
from app.services.inventory import (
    SoldOutError,
    decrement_inventory,
    iter_nights,
    restore_inventory,
)

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


def _flat_price(room: Room, check_in: date, check_out: date) -> int:
    """Milestone-5 placeholder. Strategy-based pricing arrives in milestone 6."""
    nights = len(iter_nights(check_in, check_out))
    return room.base_price_cents * nights


async def init_booking(
    db: AsyncSession,
    user_id: int,
    room_id: int,
    check_in: date,
    check_out: date,
    price_cents: int | None = None,
) -> Booking:
    """Acquire inventory locks, decrement, and create a RESERVED booking.

    price_cents is injected from the pricing engine in milestone 6; falls back to
    base * nights when not provided so this function stays testable in isolation.
    """
    room = await db.get(Room, room_id)
    if room is None:
        raise BookingError("room not found")

    try:
        await decrement_inventory(db, room_id=room_id, check_in=check_in, check_out=check_out)
    except SoldOutError as exc:
        raise BookingError(str(exc)) from exc

    total = price_cents if price_cents is not None else _flat_price(room, check_in, check_out)

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
