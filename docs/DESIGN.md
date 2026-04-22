# Design Decisions

This document covers the non-obvious decisions in the hotel booking API so they can be defended in an interview.

## 1. Concurrency model: pessimistic locking

**The problem.** Two customers try to book the last available room at the same time. Naive code (`SELECT available`, check `> 0`, `UPDATE available = available - 1`) gives both transactions the same "1" and decrements to -1.

**The choice.** `SELECT ... FOR UPDATE` on `room_inventory` rows, ordered by date, inside the same transaction that decrements. Postgres acquires a row-level write lock; the second transaction blocks until the first commits. When it unblocks it re-reads the row, sees 0, and we raise a 409.

**Why pessimistic over optimistic.** Optimistic locking (version column + retry loop) works for low-contention writes. Inventory on a popular booking date is high-contention. Retrying under conflict storms wastes CPU and produces worse tail latency than blocking.

**What can go wrong.**
- **Deadlocks.** Avoided by always locking rows in a stable order (`ORDER BY date`).
- **Long transactions hold locks.** We do zero network I/O inside the locked transaction — pricing math is pure, Stripe is called *after* commit.
- **Lock timeouts / connection drops.** Postgres auto-releases locks on transaction abort; the client gets a 5xx and retries.

## 2. Booking state machine

States: `RESERVED → CONFIRMED`, `RESERVED → CANCELLED`, `CONFIRMED → CANCELLED`.

Enforced by an explicit `ALLOWED_TRANSITIONS` dict in [app/services/booking.py](../app/services/booking.py) — not by if-else scattered through the codebase. Any attempt to move `CANCELLED → CONFIRMED` raises `InvalidTransition`.

**Why a dict over conditionals.** New transitions become one-line additions. Invariant violations surface at the edit site, not at runtime in production.

**Reaper interaction.** The reaper scans for `RESERVED` bookings older than `RESERVATION_HOLD_MINUTES` (default 15) and cancels them. If Stripe confirms a payment for a booking the reaper already cancelled, the payment handler sees `InvalidTransition`, logs a manual-refund signal, and leaves the payment as `SUCCEEDED` so the back-office can reconcile. The only way this happens is if Stripe takes > 15 minutes; we set the hold generously above the 95th-percentile checkout time.

## 3. Pricing: Strategy pattern

[app/services/pricing.py](../app/services/pricing.py) defines four strategies that compose left-to-right via `PricingEngine`:

| Strategy | Rule |
|---|---|
| `BasePricing` | seed price = `base_price_cents * nights` |
| `OccupancyPricing` | tier-based uplift on avg % sold across the stay |
| `SurgePricing` | +25% if any night has ≤ 20% availability remaining |
| `HolidayPricing` | +40% if any night is on a hardcoded holiday |

**Why Strategy over nested conditionals.** Adding a "loyalty discount" is `class LoyaltyDiscount(PricingStrategy)` + append to the engine list. No existing code changes. Open-Closed.

**Order matters.** `SurgePricing` applies to a price that already reflects base; `HolidayPricing` compounds on top of surge. If we wanted additive rather than compound, we'd split each strategy into `(delta_pct, reason)` and sum at the end — noted but unnecessary for this scope.

**Price is snapshotted.** `bookings.total_price_cents` is stored at init time. A price change tomorrow does not retroactively alter yesterday's booking.

## 4. Auth: dual-token JWT

- **Access token**: 15 min, short-lived, carried on every request.
- **Refresh token**: 7 days, long-lived, used only against `POST /auth/refresh`.

If an access token leaks via logs/proxies, the window of abuse is 15 min. Refresh tokens never touch general endpoints, so their leak surface is smaller.

**Limitations (honest).** No token rotation, no revocation list — if a refresh token is compromised, the attacker has 7 days. Production would add a `refresh_token_jti` table with rotation and device binding. Out of scope for v1 but flagged in "future extensions" in the README.

## 5. Stripe integration

Flow:
1. `POST /bookings/{id}/payments` → server creates a `PaymentIntent` with idempotency key `booking-{id}`. Returns `client_secret` to the client.
2. Client confirms payment directly with Stripe using `client_secret` (never hits our server).
3. Stripe POSTs to `/webhooks/stripe` with signed payload.
4. We verify the signature (HMAC-SHA256 against `STRIPE_WEBHOOK_SECRET`), then dispatch by event type.

**Why webhooks instead of polling.** Polling wastes calls and adds latency to confirmation. Webhooks arrive within seconds.

**What if the webhook arrives twice?** Each Stripe event has a unique `id`. We write it to `processed_stripe_events` as the last step of handling; a repeat lookup returns `"duplicate"` and short-circuits. Safe because the DB unique constraint would reject a second insert anyway.

**What if our server is down when Stripe calls?** Stripe retries with exponential backoff for up to 3 days. Once we're back, the event goes through.

**Reaper race.** See state-machine section — handled by refusing to force an illegal transition and logging a refund signal.

## 6. Schema choices

- `bookings` + `guests` + `booking_guests`: classic N:M. A guest can appear on multiple bookings (family member booking several trips); a booking can have multiple guests.
- `payments.booking_id` is `UNIQUE` — one-to-one with `bookings`. Enforced at the DB so the application code can't accidentally create duplicates.
- `room_inventory` unique `(room_id, date)` — prevents double-seeding.
- Check constraints `available_units >= 0` and `available_units <= total_units` — defense in depth: even if the application logic has a bug, Postgres refuses the bad write.
