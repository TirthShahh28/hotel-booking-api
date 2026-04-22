from pydantic import BaseModel, Field


class HotelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=500)


class HotelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, min_length=1, max_length=500)


class HotelOut(BaseModel):
    id: int
    name: str
    city: str
    address: str
    owner_id: int

    model_config = {"from_attributes": True}


class RoomCreate(BaseModel):
    room_type: str = Field(min_length=1, max_length=80)
    capacity: int = Field(ge=1, le=20)
    base_price_cents: int = Field(ge=0)


class RoomUpdate(BaseModel):
    room_type: str | None = Field(default=None, min_length=1, max_length=80)
    capacity: int | None = Field(default=None, ge=1, le=20)
    base_price_cents: int | None = Field(default=None, ge=0)


class RoomOut(BaseModel):
    id: int
    hotel_id: int
    room_type: str
    capacity: int
    base_price_cents: int

    model_config = {"from_attributes": True}


class HotelWithRooms(HotelOut):
    rooms: list[RoomOut] = []
