from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from app.services.pricing import (
    BasePricing,
    HolidayPricing,
    OccupancyPricing,
    PricingContext,
    PricingEngine,
    SurgePricing,
)


@dataclass
class FakeInventory:
    date: date
    total_units: int
    available_units: int


def _ctx(
    base: int,
    start: date,
    nights: int,
    total_units: int = 10,
    available: int | list[int] = 10,
) -> PricingContext:
    rows: list[FakeInventory] = []
    for i in range(nights):
        a = available[i] if isinstance(available, list) else available
        rows.append(FakeInventory(date=start + timedelta(days=i), total_units=total_units, available_units=a))
    return PricingContext(
        base_price_cents=base,
        check_in=start,
        check_out=start + timedelta(days=nights),
        inventory_rows=rows,  # type: ignore[arg-type]
    )


def test_base_pricing_multiplies_by_nights() -> None:
    ctx = _ctx(10_000, date(2026, 6, 1), nights=3)
    assert BasePricing().apply(0, ctx) == 30_000


def test_surge_applies_when_any_night_scarce() -> None:
    ctx = _ctx(10_000, date(2026, 6, 1), nights=2, total_units=10, available=[10, 1])
    engine = PricingEngine([BasePricing(), SurgePricing()])
    # base = 20_000, surge triggers, *1.25 -> 25_000
    assert engine.compute(ctx) == 25_000


def test_surge_does_not_apply_when_plenty() -> None:
    ctx = _ctx(10_000, date(2026, 6, 1), nights=2, total_units=10, available=10)
    engine = PricingEngine([BasePricing(), SurgePricing()])
    assert engine.compute(ctx) == 20_000


def test_holiday_uplift() -> None:
    ctx = _ctx(10_000, date(2026, 12, 24), nights=2)
    engine = PricingEngine([BasePricing(), HolidayPricing()])
    # base = 20_000, includes Dec 24 & 25 -> *1.40 -> 28_000
    assert engine.compute(ctx) == 28_000


def test_occupancy_tier() -> None:
    # 8/10 sold on each night -> 80% -> matches 0.7 tier (1.15)
    ctx = _ctx(10_000, date(2026, 6, 1), nights=2, total_units=10, available=[2, 2])
    engine = PricingEngine([BasePricing(), OccupancyPricing()])
    assert engine.compute(ctx) == int(20_000 * 1.15)


def test_combined_surge_and_holiday_compound() -> None:
    ctx = _ctx(10_000, date(2026, 12, 25), nights=2, total_units=10, available=[1, 1])
    engine = PricingEngine([BasePricing(), SurgePricing(), HolidayPricing()])
    # 20_000 -> surge 25_000 -> holiday 25_000 * 1.40 = 35_000
    assert engine.compute(ctx) == 35_000


def test_engine_rejects_empty_strategies() -> None:
    with pytest.raises(ValueError):
        PricingEngine([])
