from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.core import security


@pytest.mark.asyncio
async def test_signup_creates_customer(client: AsyncClient) -> None:
    r = await client.post("/auth/signup", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == "a@b.com"
    assert data["role"] == "CUSTOMER"


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient) -> None:
    payload = {"email": "dupe@b.com", "password": "password123"}
    await client.post("/auth/signup", json=payload)
    r = await client.post("/auth/signup", json=payload)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_login_returns_token_pair(client: AsyncClient) -> None:
    await client.post("/auth/signup", json={"email": "l@b.com", "password": "password123"})
    r = await client.post("/auth/login", json={"email": "l@b.com", "password": "password123"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data and "refresh_token" in data


@pytest.mark.asyncio
async def test_login_bad_password(client: AsyncClient) -> None:
    await client.post("/auth/signup", json={"email": "bp@b.com", "password": "password123"})
    r = await client.post("/auth/login", json={"email": "bp@b.com", "password": "wrong-password"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_refresh_exchange(client: AsyncClient) -> None:
    await client.post("/auth/signup", json={"email": "r@b.com", "password": "password123"})
    login = await client.post("/auth/login", json={"email": "r@b.com", "password": "password123"})
    refresh_token = login.json()["refresh_token"]

    r = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_refresh_rejects_access_token(client: AsyncClient) -> None:
    await client.post("/auth/signup", json={"email": "x@b.com", "password": "password123"})
    login = await client.post("/auth/login", json={"email": "x@b.com", "password": "password123"})
    access = login.json()["access_token"]

    r = await client.post("/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


def test_expired_token_raises() -> None:
    token = security._encode(
        subject="1",
        token_type=security.ACCESS,
        expires_delta=timedelta(seconds=-1),
        extra={"role": "CUSTOMER"},
    )
    with pytest.raises(ValueError):
        security.decode_token(token, expected_type=security.ACCESS)
