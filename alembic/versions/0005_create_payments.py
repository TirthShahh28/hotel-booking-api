"""create payments and processed_stripe_events

Revision ID: 0005_create_payments
Revises: 0004_create_bookings
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_create_payments"
down_revision: Union[str, None] = "0004_create_bookings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    payment_status = sa.Enum("PENDING", "SUCCEEDED", "FAILED", name="payment_status")
    payment_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("bookings.id"),
            nullable=False,
        ),
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            payment_status,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("booking_id", name="uq_payments_booking_id"),
        sa.UniqueConstraint(
            "stripe_payment_intent_id", name="uq_payments_stripe_payment_intent_id"
        ),
    )
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"])
    op.create_index(
        "ix_payments_stripe_payment_intent_id", "payments", ["stripe_payment_intent_id"]
    )

    op.create_table(
        "processed_stripe_events",
        sa.Column("event_id", sa.String(length=255), primary_key=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("processed_stripe_events")
    op.drop_index("ix_payments_stripe_payment_intent_id", table_name="payments")
    op.drop_index("ix_payments_booking_id", table_name="payments")
    op.drop_table("payments")
    sa.Enum(name="payment_status").drop(op.get_bind(), checkfirst=True)
