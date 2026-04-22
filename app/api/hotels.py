from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.hotel import Hotel, Room
from app.models.inventory import RoomInventory
from app.schemas.hotel import HotelOut, HotelWithRooms
from app.services.inventory import iter_nights

router = APIRouter(prefix="/hotels", tags=["hotels"])


@router.get("/search", response_model=list[HotelOut])
async def search_hotels(
    city: str = Query(min_length=1),
    check_in: date | None = None,
    check_out: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Hotel]:
    if check_in and check_out and check_in >= check_out:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")

    stmt = (
        select(Hotel)
        .join(Room, Room.hotel_id == Hotel.id)
        .where(Hotel.city.ilike(city))
        .distinct()
    )

    if check_in and check_out:
        nights = iter_nights(check_in, check_out)
        # A room is available iff every night in range has available_units > 0.
        # Count matching inventory rows per room; only keep rooms where count == len(nights).
        available_rooms = (
            select(RoomInventory.room_id)
            .where(
                RoomInventory.date.in_(nights),
                RoomInventory.available_units > 0,
            )
            .group_by(RoomInventory.room_id)
            .having(func.count(RoomInventory.id) == len(nights))
        )
        stmt = stmt.where(Room.id.in_(available_rooms))

    result = await db.scalars(stmt)
    return list(result.all())


@router.get("/{hotel_id}", response_model=HotelWithRooms)
async def get_hotel(hotel_id: int, db: AsyncSession = Depends(get_db)) -> Hotel:
    stmt = select(Hotel).options(selectinload(Hotel.rooms)).where(Hotel.id == hotel_id)
    hotel = await db.scalar(stmt)
    if hotel is None:
        raise HTTPException(status_code=404, detail="hotel not found")
    return hotel
