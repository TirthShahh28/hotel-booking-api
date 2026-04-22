from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User, UserRole


async def _make_admin(db: AsyncSession, email: str = "admin@h.com") -> User:
    admin = User(email=email, password_hash=hash_password("password123"), role=UserRole.ADMIN)
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


async def _admin_token(client: AsyncClient, db: AsyncSession, email: str = "admin@h.com") -> str:
    await _make_admin(db, email=email)
    r = await client.post("/auth/login", json={"email": email, "password": "password123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_customer_cannot_create_hotel(client: AsyncClient) -> None:
    await client.post("/auth/signup", json={"email": "c@h.com", "password": "password123"})
    login = await client.post("/auth/login", json={"email": "c@h.com", "password": "password123"})
    token = login.json()["access_token"]

    r = await client.post(
        "/admin/hotels",
        json={"name": "Hi", "city": "NYC", "address": "1 Main"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_creates_hotel_and_room(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _admin_token(client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/admin/hotels",
        json={"name": "Grand", "city": "NYC", "address": "1 Main"},
        headers=headers,
    )
    assert r.status_code == 201
    hotel_id = r.json()["id"]

    r = await client.post(
        f"/admin/hotels/{hotel_id}/rooms",
        json={"room_type": "Deluxe", "capacity": 2, "base_price_cents": 25000},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["hotel_id"] == hotel_id


@pytest.mark.asyncio
async def test_search_returns_hotels_with_rooms(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _admin_token(client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/admin/hotels",
        json={"name": "Grand", "city": "NYC", "address": "1 Main"},
        headers=headers,
    )
    hotel_id = r.json()["id"]
    await client.post(
        f"/admin/hotels/{hotel_id}/rooms",
        json={"room_type": "Deluxe", "capacity": 2, "base_price_cents": 25000},
        headers=headers,
    )

    r = await client.get("/hotels/search", params={"city": "NYC"})
    assert r.status_code == 200
    assert any(h["id"] == hotel_id for h in r.json())


@pytest.mark.asyncio
async def test_search_empty_when_no_rooms(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _admin_token(client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/admin/hotels",
        json={"name": "Empty", "city": "Boston", "address": "1 Main"},
        headers=headers,
    )

    r = await client.get("/hotels/search", params={"city": "Boston"})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_search_invalid_date_range(client: AsyncClient) -> None:
    r = await client.get(
        "/hotels/search",
        params={"city": "NYC", "check_in": "2026-05-10", "check_out": "2026-05-01"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_admin_cannot_edit_others_hotel(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    t1 = await _admin_token(client, db_session, email="a1@h.com")
    r = await client.post(
        "/admin/hotels",
        json={"name": "A1", "city": "NYC", "address": "1 Main"},
        headers={"Authorization": f"Bearer {t1}"},
    )
    hotel_id = r.json()["id"]

    t2 = await _admin_token(client, db_session, email="a2@h.com")
    r = await client.put(
        f"/admin/hotels/{hotel_id}",
        json={"name": "Stolen"},
        headers={"Authorization": f"Bearer {t2}"},
    )
    assert r.status_code == 403
