# hotel-booking-api

A production-grade hotel booking REST API built with FastAPI, PostgreSQL, and Stripe.

Inspired by Airbnb's booking model. Designed to demonstrate real-world backend concerns: concurrent inventory control, booking state machines, dynamic pricing, and third-party payment integration.

## Features

- JWT auth with access + refresh tokens (bcrypt password hashing)
- Role-based access control (admin / customer)
- Hotel & room management (admin) + public search with date-range availability
- Per-day room inventory with **pessimistic locking** (`SELECT ... FOR UPDATE`) to prevent overbooking under concurrency
- Booking lifecycle state machine (`RESERVED` → `CONFIRMED` / `CANCELLED`) with explicit transition enforcement
- Background reaper that releases expired `RESERVED` holds
- Dynamic pricing via Strategy pattern (base / surge / holiday / occupancy)
- Stripe payment integration with webhook signature verification and idempotent event handling

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Framework | FastAPI (async) |
| DB | PostgreSQL 16 |
| ORM | SQLAlchemy 2.0 (async) + Alembic |
| Validation | Pydantic v2 |
| Auth | python-jose (JWT) + passlib (bcrypt) |
| Payments | Stripe |
| Tests | pytest + httpx + pytest-asyncio |
| Infra | Docker Compose |

## Run locally

```bash
cp .env.example .env
docker compose up -d db
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

Docs: http://localhost:8000/docs

## Project layout

```
app/
  api/          # route handlers grouped by domain
  core/         # config, security, deps
  db/           # session, base class
  models/       # SQLAlchemy ORM models
  schemas/      # Pydantic DTOs
  services/     # business logic (booking, pricing, payments)
alembic/        # migrations
tests/
```

## Design decisions

See [docs/DESIGN.md](docs/DESIGN.md) — covers the concurrency model, state machine, pricing strategy, and Stripe integration.

## License

MIT
