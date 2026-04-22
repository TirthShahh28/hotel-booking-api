from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.booking import BookingStatus


class BookingInitRequest(BaseModel):
    room_id: int
    check_in: date
    check_out: date

    @model_validator(mode="after")
    def _validate_range(self) -> "BookingInitRequest":
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


class GuestCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    email: EmailStr | None = None


class GuestOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone: str | None = None
    email: str | None = None

    model_config = {"from_attributes": True}


class BookingOut(BaseModel):
    id: int
    user_id: int
    room_id: int
    check_in: date
    check_out: date
    status: BookingStatus
    total_price_cents: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingWithGuests(BookingOut):
    guests: list[GuestOut] = []
