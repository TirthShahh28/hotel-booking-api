from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.payments import _gateway
from app.core.security import hash_password
from app.main import app
from app.models.booking import Booking, BookingStatus
from app.models.hotel import Hotel, Room
from app.models.payment import Payment, PaymentStatus
from app.models.user import User, UserRole
from app.services.inventory import seed_room_inventory
from app.services.payments import handle_stripe_event


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._next_intent = 0

    def create_payment_intent(
        self, amount_cents: int, idempotency_key: str, metadata: dict[str, str]
    ) -> dict[str, Any]:
        self._next_intent += 1
        intent_id = f"pi_fake_{self._next_intent}"
        self.calls.append(
            {
                "amount": amount_cents,
                "idempotency_key": idempotency_key,
                "metadata": metadata,
                "id": intent_id,
            }
        )
        return {"id": intent_id, "client_secret": f"cs_{intent_id}_secret"}

    def construct_event(self, payload: bytes, sig_header: str) -> dict[str, Any]:
        if sig_header == "bad":
            raise ValueError("invalid signature")
        import json

        return json.loads(payload)


@pytest.fixture
def fake_gateway() -> FakeGateway:
    gw = FakeGateway()
    app.dependency_overrides[_gateway] = lambda: gw
    yield gw
    app.dependency_overrides.pop(_gateway, None)


async def _bootstrap_booking(db: AsyncSession) -> tuple[User, Booking]:
    customer = User(
        email="pay@b.com", password_hash=hash_password("password123"), role=UserRole.CUSTOMER
    )
    owner = User(
        email="oown@b.com", password_hash=hash_password("password123"), role=UserRole.ADMIN
    )
    db.add_all([customer, owner])
    await db.flush()

    hotel = Hotel(name="Grand", city="NYC", address="1 Main", owner_id=owner.id)
    db.add(hotel)
    await db.flush()
    room = Room(hotel_id=hotel.id, room_type="Std", capacity=2, base_price_cents=20000)
    db.add(room)
    await db.flush()
    await seed_room_inventory(db, room_id=room.id, total_units=1, horizon_days=5)

    start = date.today()
    booking = Booking(
        user_id=customer.id,
        room_id=room.id,
        check_in=start,
        check_out=start + timedelta(days=1),
        status=BookingStatus.RESERVED,
        total_price_cents=20000,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return customer, booking


async def _token(client: AsyncClient, email: str) -> str:
    r = await client.post("/auth/login", json={"email": email, "password": "password123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_create_payment_returns_client_secret(
    client: AsyncClient, db_session: AsyncSession, fake_gateway: FakeGateway
) -> None:
    customer, booking = await _bootstrap_booking(db_session)
    token = await _token(client, customer.email)

    r = await client.post(
        f"/bookings/{booking.id}/payments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["client_secret"].startswith("cs_pi_fake_")
    assert body["amount_cents"] == 20000

    assert len(fake_gateway.calls) == 1
    assert fake_gateway.calls[0]["idempotency_key"] == f"booking-{booking.id}"


@pytest.mark.asyncio
async def test_second_payment_attempt_rejected(
    client: AsyncClient, db_session: AsyncSession, fake_gateway: FakeGateway
) -> None:
    customer, booking = await _bootstrap_booking(db_session)
    token = await _token(client, customer.email)
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await client.post(f"/bookings/{booking.id}/payments", headers=headers)
    assert r1.status_code == 201
    r2 = await client.post(f"/bookings/{booking.id}/payments", headers=headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_webhook_rejects_missing_signature(client: AsyncClient) -> None:
    r = await client.post("/webhooks/stripe", content=b"{}")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(
    client: AsyncClient, fake_gateway: FakeGateway
) -> None:
    r = await client.post(
        "/webhooks/stripe", content=b"{}", headers={"Stripe-Signature": "bad"}
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_webhook_success_confirms_booking(
    db_session: AsyncSession,
) -> None:
    _, booking = await _bootstrap_booking(db_session)

    payment = Payment(
        booking_id=booking.id,
        stripe_payment_intent_id="pi_success_1",
        amount_cents=booking.total_price_cents,
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()

    event = {
        "id": "evt_1",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_success_1"}},
    }
    result = await handle_stripe_event(db_session, event)
    await db_session.commit()
    assert result == "ok"

    refreshed_booking = await db_session.get(Booking, booking.id)
    refreshed_payment = await db_session.scalar(
        select(Payment).where(Payment.id == payment.id)
    )
    assert refreshed_booking is not None and refreshed_booking.status == BookingStatus.CONFIRMED
    assert refreshed_payment is not None and refreshed_payment.status == PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_webhook_duplicate_event_is_no_op(db_session: AsyncSession) -> None:
    _, booking = await _bootstrap_booking(db_session)
    payment = Payment(
        booking_id=booking.id,
        stripe_payment_intent_id="pi_dup_1",
        amount_cents=booking.total_price_cents,
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()

    event = {
        "id": "evt_dup",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_dup_1"}},
    }
    r1 = await handle_stripe_event(db_session, event)
    await db_session.commit()
    r2 = await handle_stripe_event(db_session, event)
    await db_session.commit()
    assert r1 == "ok"
    assert r2 == "duplicate"


@pytest.mark.asyncio
async def test_webhook_failed_event_marks_payment_failed(db_session: AsyncSession) -> None:
    _, booking = await _bootstrap_booking(db_session)
    payment = Payment(
        booking_id=booking.id,
        stripe_payment_intent_id="pi_fail_1",
        amount_cents=booking.total_price_cents,
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()

    event = {
        "id": "evt_fail",
        "type": "payment_intent.payment_failed",
        "data": {"object": {"id": "pi_fail_1"}},
    }
    await handle_stripe_event(db_session, event)
    await db_session.commit()

    refreshed_booking = await db_session.get(Booking, booking.id)
    refreshed_payment = await db_session.scalar(
        select(Payment).where(Payment.id == payment.id)
    )
    assert refreshed_booking is not None and refreshed_booking.status == BookingStatus.RESERVED
    assert refreshed_payment is not None and refreshed_payment.status == PaymentStatus.FAILED
