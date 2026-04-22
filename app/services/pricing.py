from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from app.models.inventory import RoomInventory


@dataclass(frozen=True)
class PricingContext:
    base_price_cents: int
    check_in: date
    check_out: date
    inventory_rows: list[RoomInventory]  # one per night in [check_in, check_out)


class PricingStrategy(ABC):
    """A pricing strategy takes the running price and returns the adjusted price.

    Strategies are composed in order by PricingEngine; each one sees the price
    produced by the previous strategy, so order matters.
    """

    @abstractmethod
    def apply(self, current_cents: int, ctx: PricingContext) -> int: ...


class BasePricing(PricingStrategy):
    """Initializes the price to base_price * number_of_nights."""

    def apply(self, current_cents: int, ctx: PricingContext) -> int:
        nights = len(ctx.inventory_rows)
        return ctx.base_price_cents * nights


class SurgePricing(PricingStrategy):
    """If any night is nearly sold out (<= threshold), mark up by `multiplier`.

    Simulates Airbnb-style demand pricing when supply is scarce.
    """

    def __init__(self, scarcity_ratio: float = 0.2, multiplier: float = 1.25) -> None:
        self.scarcity_ratio = scarcity_ratio
        self.multiplier = multiplier

    def apply(self, current_cents: int, ctx: PricingContext) -> int:
        scarce = any(
            (row.available_units / row.total_units) <= self.scarcity_ratio
            for row in ctx.inventory_rows
            if row.total_units > 0
        )
        return int(current_cents * self.multiplier) if scarce else current_cents


class HolidayPricing(PricingStrategy):
    """Flat uplift when any night in the stay falls on a holiday."""

    DEFAULT_HOLIDAYS: frozenset[tuple[int, int]] = frozenset(
        {
            (1, 1),
            (7, 4),
            (12, 24),
            (12, 25),
            (12, 31),
        }
    )

    def __init__(
        self,
        holidays: frozenset[tuple[int, int]] | None = None,
        multiplier: float = 1.40,
    ) -> None:
        self.holidays = holidays if holidays is not None else self.DEFAULT_HOLIDAYS
        self.multiplier = multiplier

    def apply(self, current_cents: int, ctx: PricingContext) -> int:
        hit_holiday = any(
            (row.date.month, row.date.day) in self.holidays for row in ctx.inventory_rows
        )
        return int(current_cents * self.multiplier) if hit_holiday else current_cents


class OccupancyPricing(PricingStrategy):
    """Tiered multiplier based on average % of inventory sold across the stay."""

    def __init__(self, tiers: list[tuple[float, float]] | None = None) -> None:
        # (sold_ratio_threshold, multiplier). Evaluated in order; first match wins.
        self.tiers = tiers or [
            (0.9, 1.30),
            (0.7, 1.15),
            (0.5, 1.05),
        ]

    def apply(self, current_cents: int, ctx: PricingContext) -> int:
        if not ctx.inventory_rows:
            return current_cents
        sold_ratios = [
            (row.total_units - row.available_units) / row.total_units
            for row in ctx.inventory_rows
            if row.total_units > 0
        ]
        if not sold_ratios:
            return current_cents
        avg = sum(sold_ratios) / len(sold_ratios)
        for threshold, mult in self.tiers:
            if avg >= threshold:
                return int(current_cents * mult)
        return current_cents


class PricingEngine:
    """Composes strategies left-to-right. BasePricing must be first."""

    def __init__(self, strategies: list[PricingStrategy]) -> None:
        if not strategies:
            raise ValueError("at least one strategy (BasePricing) is required")
        self.strategies = strategies

    def compute(self, ctx: PricingContext) -> int:
        price = 0
        for strategy in self.strategies:
            price = strategy.apply(price, ctx)
        return price


def default_engine() -> PricingEngine:
    return PricingEngine(
        [
            BasePricing(),
            OccupancyPricing(),
            SurgePricing(),
            HolidayPricing(),
        ]
    )
