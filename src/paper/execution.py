"""Simulate a market order by walking real order-book depth.

We never fill at the midpoint or a single "nice" price. We consume levels from
best outward, so large orders pay progressively worse prices (slippage) and may
only partially fill if the book is thin. Fees are applied on the traded notional
and must be supplied per market (never hard-coded).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from src.domain.models import Level


@dataclass(frozen=True)
class Fill:
    shares_filled: Decimal
    avg_price: Decimal  # realised average execution price, [0, 1]
    notional: Decimal  # shares_filled * avg_price, before fees
    fee: Decimal  # notional * fee_rate
    slippage: Decimal  # avg_price - reference_price (>= 0 for a buy)
    filled_fully: bool
    levels_used: int

    @property
    def total_cost(self) -> Decimal:
        """Cash out the door for a buy: notional plus fee."""
        return self.notional + self.fee


_ZERO = Decimal(0)


def _empty_fill() -> Fill:
    return Fill(_ZERO, _ZERO, _ZERO, _ZERO, _ZERO, False, 0)


def simulate_buy(
    asks: Sequence[Level],
    target_shares: Decimal,
    *,
    fee_rate: Decimal,
    reference_price: Decimal | None = None,
) -> Fill:
    """Buy up to ``target_shares`` by consuming ``asks`` (ascending price).

    ``reference_price`` is the benchmark for slippage; defaults to the best ask
    (the price naively assumed available). Partial fills happen when book depth
    is insufficient.
    """
    if target_shares <= 0 or not asks:
        return _empty_fill()

    remaining = target_shares
    filled = _ZERO
    cost = _ZERO
    levels_used = 0

    for level in asks:
        if remaining <= 0:
            break
        take = min(remaining, level.size)
        if take <= 0:
            continue
        cost += take * level.price
        filled += take
        remaining -= take
        levels_used += 1

    if filled <= 0:
        return _empty_fill()

    avg_price = cost / filled
    reference = reference_price if reference_price is not None else asks[0].price
    fee = cost * fee_rate
    slippage = avg_price - reference
    return Fill(
        shares_filled=filled,
        avg_price=avg_price,
        notional=cost,
        fee=fee,
        slippage=slippage,
        filled_fully=filled >= target_shares,
        levels_used=levels_used,
    )


def simulate_sell(
    bids: Sequence[Level],
    target_shares: Decimal,
    *,
    fee_rate: Decimal,
    reference_price: Decimal | None = None,
) -> Fill:
    """Sell up to ``target_shares`` by consuming ``bids`` (descending price).

    Slippage is reported as ``reference_price - avg_price`` (>= 0), i.e. how
    much worse than the benchmark the sale executed.
    """
    if target_shares <= 0 or not bids:
        return _empty_fill()

    remaining = target_shares
    filled = _ZERO
    proceeds = _ZERO
    levels_used = 0

    for level in bids:
        if remaining <= 0:
            break
        take = min(remaining, level.size)
        if take <= 0:
            continue
        proceeds += take * level.price
        filled += take
        remaining -= take
        levels_used += 1

    if filled <= 0:
        return _empty_fill()

    avg_price = proceeds / filled
    reference = reference_price if reference_price is not None else bids[0].price
    fee = proceeds * fee_rate
    slippage = reference - avg_price
    return Fill(
        shares_filled=filled,
        avg_price=avg_price,
        notional=proceeds,
        fee=fee,
        slippage=slippage,
        filled_fully=filled >= target_shares,
        levels_used=levels_used,
    )
