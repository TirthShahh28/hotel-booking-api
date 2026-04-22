"""create room_inventory

Revision ID: 0003_create_room_inventory
Revises: 0002_create_hotels_rooms
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_create_room_inventory"
down_revision: Union[str, None] = "0002_create_hotels_rooms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "room_inventory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "room_id",
            sa.Integer(),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("total_units", sa.Integer(), nullable=False),
        sa.Column("available_units", sa.Integer(), nullable=False),
        sa.UniqueConstraint("room_id", "date", name="uq_room_inventory_room_date"),
        sa.CheckConstraint("available_units >= 0", name="ck_room_inventory_non_negative"),
        sa.CheckConstraint(
            "available_units <= total_units", name="ck_room_inventory_le_total"
        ),
    )
    op.create_index("ix_room_inventory_room_id", "room_inventory", ["room_id"])
    op.create_index("ix_room_inventory_date", "room_inventory", ["date"])


def downgrade() -> None:
    op.drop_index("ix_room_inventory_date", table_name="room_inventory")
    op.drop_index("ix_room_inventory_room_id", table_name="room_inventory")
    op.drop_table("room_inventory")
