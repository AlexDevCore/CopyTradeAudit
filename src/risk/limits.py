"""Deterministic risk limits applied before any (virtual) trade.

These sit between the signal and the paper portfolio: even a valid BUY signal is
sized down or refused here if it would breach an exposure cap or run on stale
data. All money is Decimal; no floats leak into cash figures.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.domain.params import DEFAULTS, StrategyParams


def position_size(balance: Decimal, params: StrategyParams = DEFAULTS) -> Decimal:
    """Target stake for one signal: bet fraction, hard-capped per position."""
    target = balance * params.bet_fraction
    cap = balance * params.max_position_fraction
    return min(target, cap)


def within_correlated_group_limit(
    group_exposure: Decimal,
    new_size: Decimal,
    balance: Decimal,
    params: StrategyParams = DEFAULTS,
) -> bool:
    """True if adding ``new_size`` keeps the correlated group under its cap.

    A correlated group is markets sharing one underlying event (one outcome ->
    several markets), so concentration is not hidden across "different" markets.
    """
    cap = balance * params.max_correlated_group_fraction
    return (group_exposure + new_size) <= cap


def is_data_stale(age_sec: int, params: StrategyParams = DEFAULTS) -> bool:
    return age_sec > params.data_staleness_sec


@dataclass(frozen=True)
class RiskCheck:
    approved: bool
    size: Decimal
    reason: str


def check_trade(
    balance: Decimal,
    group_exposure: Decimal,
    data_age_sec: int,
    params: StrategyParams = DEFAULTS,
) -> RiskCheck:
    """Approve/deny a prospective trade and return the risk-capped size."""
    if is_data_stale(data_age_sec, params):
        return RiskCheck(False, Decimal(0), f"stale data ({data_age_sec}s)")

    size = position_size(balance, params)
    if size <= 0:
        return RiskCheck(False, Decimal(0), "non-positive size (no balance)")

    if not within_correlated_group_limit(group_exposure, size, balance, params):
        cap = balance * params.max_correlated_group_fraction
        room = cap - group_exposure
        if room <= 0:
            return RiskCheck(False, Decimal(0), "correlated group limit reached")
        # Size down to the remaining room rather than refuse outright.
        return RiskCheck(True, room, "sized down to correlated group limit")

    return RiskCheck(True, size, "approved")
