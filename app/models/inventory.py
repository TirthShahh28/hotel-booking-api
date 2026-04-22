from __future__ import annotations

from datetime import date as date_type

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RoomInventory(Base):
    __tablename__ = "room_inventory"
    __table_args__ = (
        UniqueConstraint("room_id", "date", name="uq_room_inventory_room_date"),
        CheckConstraint("available_units >= 0", name="ck_room_inventory_non_negative"),
        CheckConstraint("available_units <= total_units", name="ck_room_inventory_le_total"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    total_units: Mapped[int] = mapped_column(Integer, nullable=False)
    available_units: Mapped[int] = mapped_column(Integer, nullable=False)
