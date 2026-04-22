from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    rooms: Mapped[list[Room]] = relationship(back_populates="hotel", cascade="all, delete-orphan")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    room_type: Mapped[str] = mapped_column(String(80), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    base_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    hotel: Mapped[Hotel] = relationship(back_populates="rooms")
