from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.booking import Booking, BookingStatus
from app.models.hotel import Hotel, Room
from app.models.inventory import RoomInventory
from app.models.user import User, UserRole
from app.services.booking import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    assert_transition,
    reap_expired_reservations,
)
from app.services.inventory import seed_room_inventory


async def _bootstrap(db: AsyncSession) -> tuple[User, Room]:
    customer = User(
        email="cust@b.com", password_hash=hash_password("password123"), role=UserRole.CUSTOMER
    )
    owner = User(
        email="own@b.com", password_hash=hash_password("password123"), role=UserRole.ADMIN
    )
    db.add_all([customer, owner])
    await db.flush()

    hotel = Hotel(name="Grand", city="NYC", address="1 Main", owner_id=owner.id)
    db.add(hotel)
    await db.flush()

    room = Room(hotel_id=hotel.id, room_type="Deluxe", capacity=2, base_price_cents=15000)
    db.add(room)
    await db.flush()

    await seed_room_inventory(db, room_id=room.id, total_units=1, horizon_days=10)
    await db.commit()
    return customer, room


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post("/auth/login", json={"email": email, "password": "password123"})
    return r.json()["access_token"]


def test_allowed_transitions_are_explicit() -> None:
    assert BookingStatus.CONFIRMED in ALLOWED_TRANSITIONS[BookingStatus.RESERVED]
    assert BookingStatus.CANCELLED in ALLOWED_TRANSITIONS[BookingStatus.RESERVED]
    assert ALLOWED_TRANSITIONS[BookingStatus.CANCELLED] == set()


def test_cancelled_to_confirmed_is_rejected() -> None:
    with pytest.raises(InvalidTransition):
        assert_transition(BookingStatus.CANCELLED, BookingStatus.CONFIRMED)


@pytest.mark.asyncio
async def test_init_booking_reserves_and_decrements(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    customer, room = await _bootstrap(db_session)
    token = await _login(client, customer.email)

    start = date.today()
    r = await client.post(
        "/bookings/init",
        json={
            "room_id": room.id,
            "check_in": start.isoformat(),
            "check_out": (start + timedelta(days=2)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "RESERVED"
    assert body["total_price_cents"] == 15000 * 2

    inv = (
        await db_session.scalars(
            select(RoomInventory).where(RoomInventory.room_id == room.id)
        )
    ).all()
    booked_nights = [i for i in inv if i.available_units == 0]
    assert len(booked_nights) == 2


@pytest.mark.asyncio
async def test_second_init_gets_409_when_sold_out(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    customer, room = await _bootstrap(db_session)
    token = await _login(client, customer.email)
    start = date.today()
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "room_id": room.id,
        "check_in": start.isoformat(),
        "check_out": (start + timedelta(days=1)).isoformat(),
    }
    r1 = await client.post("/bookings/init", json=payload, headers=headers)
    assert r1.status_code == 201
    r2 = await client.post("/bookings/init", json=payload, headers=headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_cancel_restores_inventory(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    customer, room = await _bootstrap(db_session)
    token = await _login(client, customer.email)
    headers = {"Authorization": f"Bearer {token}"}
    start = date.today()

    r = await client.post(
        "/bookings/init",
        json={
            "room_id": room.id,
            "check_in": start.isoformat(),
            "check_out": (start + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    booking_id = r.json()["id"]

    r = await client.post(f"/bookings/{booking_id}/cancel", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"

    inv = (
        await db_session.scalars(select(RoomInventory).where(RoomInventory.room_id == room.id))
    ).all()
    assert all(i.available_units == i.total_units for i in inv)


@pytest.mark.asyncio
async def test_attach_guest_to_reserved(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    customer, room = await _bootstrap(db_session)
    token = await _login(client, customer.email)
    headers = {"Authorization": f"Bearer {token}"}
    start = date.today()

    r = await client.post(
        "/bookings/init",
        json={
            "room_id": room.id,
            "check_in": start.isoformat(),
            "check_out": (start + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    booking_id = r.json()["id"]

    r = await client.post(
        f"/bookings/{booking_id}/guests",
        json={"first_name": "Ana", "last_name": "Lee"},
        headers=headers,
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_reaper_releases_stale_reservations(db_session: AsyncSession) -> None:
    customer, room = await _bootstrap(db_session)

    start = date.today()
    booking = Booking(
        user_id=customer.id,
        room_id=room.id,
        check_in=start,
        check_out=start + timedelta(days=1),
        status=BookingStatus.RESERVED,
        total_price_cents=15000,
    )
    booking.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add(booking)
    await db_session.commit()

    count = await reap_expired_reservations(db_session)
    await db_session.commit()
    assert count == 1

    refreshed = await db_session.get(Booking, booking.id)
    assert refreshed is not None and refreshed.status == BookingStatus.CANCELLED
