from __future__ import annotations

import logging
from typing import Any, Protocol

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentStatus, ProcessedStripeEvent
from app.services.booking import (
    InvalidTransition,
    assert_transition,
    confirm_booking,
)

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    pass


class StripeGateway(Protocol):
    """Thin seam so we can swap the real Stripe SDK with a fake in tests."""

    def create_payment_intent(
        self, amount_cents: int, idempotency_key: str, metadata: dict[str, str]
    ) -> dict[str, Any]: ...

    def construct_event(self, payload: bytes, sig_header: str) -> dict[str, Any]: ...


class RealStripeGateway:
    def __init__(self) -> None:
        stripe.api_key = settings.stripe_api_key

    def create_payment_intent(
        self, amount_cents: int, idempotency_key: str, metadata: dict[str, str]
    ) -> dict[str, Any]:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            metadata=metadata,
            idempotency_key=idempotency_key,
        )
        return {"id": intent.id, "client_secret": intent.client_secret}

    def construct_event(self, payload: bytes, sig_header: str) -> dict[str, Any]:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.stripe_webhook_secret,
        )
        return dict(event)


async def create_payment_for_booking(
    db: AsyncSession,
    booking: Booking,
    gateway: StripeGateway,
) -> tuple[Payment, str]:
    if booking.status != BookingStatus.RESERVED:
        raise PaymentError("payments can only be initiated for RESERVED bookings")

    existing = await db.scalar(select(Payment).where(Payment.booking_id == booking.id))
    if existing is not None:
        raise PaymentError("payment already exists for this booking")

    idempotency_key = f"booking-{booking.id}"
    intent = gateway.create_payment_intent(
        amount_cents=booking.total_price_cents,
        idempotency_key=idempotency_key,
        metadata={"booking_id": str(booking.id), "user_id": str(booking.user_id)},
    )

    payment = Payment(
        booking_id=booking.id,
        stripe_payment_intent_id=intent["id"],
        amount_cents=booking.total_price_cents,
        status=PaymentStatus.PENDING,
    )
    db.add(payment)
    await db.flush()
    return payment, intent["client_secret"]


async def _already_processed(db: AsyncSession, event_id: str) -> bool:
    return await db.get(ProcessedStripeEvent, event_id) is not None


async def _mark_processed(db: AsyncSession, event_id: str) -> None:
    db.add(ProcessedStripeEvent(event_id=event_id))
    await db.flush()


async def handle_stripe_event(db: AsyncSession, event: dict[str, Any]) -> str:
    """Apply a verified Stripe event. Safe to call twice: duplicates are no-ops."""
    event_id = event["id"]
    if await _already_processed(db, event_id):
        return "duplicate"

    event_type = event["type"]
    intent = event["data"]["object"]
    intent_id = intent["id"]

    payment = await db.scalar(
        select(Payment).where(Payment.stripe_payment_intent_id == intent_id)
    )
    if payment is None:
        logger.warning("stripe event %s referenced unknown intent %s", event_id, intent_id)
        await _mark_processed(db, event_id)
        return "unknown_intent"

    if event_type == "payment_intent.succeeded":
        payment.status = PaymentStatus.SUCCEEDED
        booking = await db.get(Booking, payment.booking_id)
        if booking is not None:
            try:
                assert_transition(booking.status, BookingStatus.CONFIRMED)
                await confirm_booking(db, booking)
            except InvalidTransition:
                # Booking already CANCELLED (e.g., reaper beat us). Leave payment SUCCEEDED
                # so the service desk can refund; do not force an illegal transition.
                logger.info(
                    "payment %s succeeded but booking %s is %s — needs manual refund",
                    payment.id,
                    booking.id,
                    booking.status.value,
                )
    elif event_type == "payment_intent.payment_failed":
        payment.status = PaymentStatus.FAILED

    await _mark_processed(db, event_id)
    return "ok"
