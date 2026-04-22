from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.db.session import get_db
from app.models.hotel import Hotel, Room
from app.models.user import User
from app.schemas.hotel import (
    HotelCreate,
    HotelOut,
    HotelUpdate,
    RoomCreate,
    RoomOut,
    RoomUpdate,
)
from app.services.inventory import seed_room_inventory

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/hotels", response_model=HotelOut, status_code=status.HTTP_201_CREATED)
async def create_hotel(
    body: HotelCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Hotel:
    hotel = Hotel(**body.model_dump(), owner_id=admin.id)
    db.add(hotel)
    await db.commit()
    await db.refresh(hotel)
    return hotel


@router.get("/hotels", response_model=list[HotelOut])
async def list_my_hotels(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[Hotel]:
    result = await db.scalars(select(Hotel).where(Hotel.owner_id == admin.id))
    return list(result.all())


async def _get_owned_hotel(hotel_id: int, admin: User, db: AsyncSession) -> Hotel:
    hotel = await db.get(Hotel, hotel_id)
    if hotel is None:
        raise HTTPException(status_code=404, detail="hotel not found")
    if hotel.owner_id != admin.id:
        raise HTTPException(status_code=403, detail="not your hotel")
    return hotel


@router.put("/hotels/{hotel_id}", response_model=HotelOut)
async def update_hotel(
    hotel_id: int,
    body: HotelUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Hotel:
    hotel = await _get_owned_hotel(hotel_id, admin, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(hotel, field, value)
    await db.commit()
    await db.refresh(hotel)
    return hotel


@router.post(
    "/hotels/{hotel_id}/rooms",
    response_model=RoomOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_room(
    hotel_id: int,
    body: RoomCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Room:
    await _get_owned_hotel(hotel_id, admin, db)
    room = Room(hotel_id=hotel_id, **body.model_dump())
    db.add(room)
    await db.flush()
    await seed_room_inventory(db, room_id=room.id, total_units=1)
    await db.commit()
    await db.refresh(room)
    return room


@router.get("/hotels/{hotel_id}/rooms", response_model=list[RoomOut])
async def list_rooms(
    hotel_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[Room]:
    await _get_owned_hotel(hotel_id, admin, db)
    result = await db.scalars(select(Room).where(Room.hotel_id == hotel_id))
    return list(result.all())


@router.put("/rooms/{room_id}", response_model=RoomOut)
async def update_room(
    room_id: int,
    body: RoomUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Room:
    room = await db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    await _get_owned_hotel(room.hotel_id, admin, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(room, field, value)
    await db.commit()
    await db.refresh(room)
    return room
