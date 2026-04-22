from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.booking import Booking
from app.models.user import User
from app.schemas.booking import (
    BookingInitRequest,
    BookingOut,
    BookingWithGuests,
    GuestCreate,
    GuestOut,
)
from app.services.booking import (
    BookingError,
    attach_guest,
    cancel_booking,
    init_booking,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


async def _load_owned(
    booking_id: int, user: User, db: AsyncSession, *, with_guests: bool = False
) -> Booking:
    stmt = select(Booking).where(Booking.id == booking_id)
    if with_guests:
        stmt = stmt.options(selectinload(Booking.guests))
    booking = await db.scalar(stmt)
    if booking is None:
        raise HTTPException(status_code=404, detail="booking not found")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="not your booking")
    return booking


@router.post("/init", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def bookings_init(
    body: BookingInitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    try:
        booking = await init_booking(
            db,
            user_id=user.id,
            room_id=body.room_id,
            check_in=body.check_in,
            check_out=body.check_out,
        )
    except BookingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(booking)
    return booking


@router.post("/{booking_id}/guests", response_model=GuestOut, status_code=status.HTTP_201_CREATED)
async def bookings_add_guest(
    booking_id: int,
    body: GuestCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GuestOut:
    booking = await _load_owned(booking_id, user, db, with_guests=True)
    try:
        guest = await attach_guest(
            db,
            booking,
            first_name=body.first_name,
            last_name=body.last_name,
            phone=body.phone,
            email=body.email,
        )
    except BookingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    return GuestOut.model_validate(guest)


@router.post("/{booking_id}/cancel", response_model=BookingOut)
async def bookings_cancel(
    booking_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    booking = await _load_owned(booking_id, user, db)
    try:
        await cancel_booking(db, booking)
    except BookingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(booking)
    return booking


@router.get("/{booking_id}", response_model=BookingWithGuests)
async def bookings_get(
    booking_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    return await _load_owned(booking_id, user, db, with_guests=True)
