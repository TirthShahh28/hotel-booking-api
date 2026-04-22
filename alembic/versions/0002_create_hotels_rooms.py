"""create hotels and rooms tables

Revision ID: 0002_create_hotels_rooms
Revises: 0001_create_users
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_create_hotels_rooms"
down_revision: Union[str, None] = "0001_create_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hotels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_hotels_city", "hotels", ["city"])

    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "hotel_id",
            sa.Integer(),
            sa.ForeignKey("hotels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("room_type", sa.String(length=80), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("base_price_cents", sa.Integer(), nullable=False),
    )
    op.create_index("ix_rooms_hotel_id", "rooms", ["hotel_id"])


def downgrade() -> None:
    op.drop_index("ix_rooms_hotel_id", table_name="rooms")
    op.drop_table("rooms")
    op.drop_index("ix_hotels_city", table_name="hotels")
    op.drop_table("hotels")
