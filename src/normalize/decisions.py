"""Turn a wallet's trades in one market into independent *decisions*.

Rules (agreed in design):
  - A decision is the wallet's *net* directional exposure, not a single trade.
  - Same-direction adds raise conviction/size but are still ONE decision.
  - A sign flip of net exposure closes the current decision (REVERSED) and
    opens a new one (``is_reversal=True``).
  - A reduction that stays the same sign keeps the decision OPEN (it is NOT a
    prediction of the opposite outcome).
  - Net returning to ~0 CLOSES the decision (early exit, not held to resolution).
  - Dust below both thresholds (absolute $ AND fraction of the trader's typical
    position) never becomes a decision.

Win/loss at resolution is computed elsewhere (scoring); this module only
reconstructs the decisions and their state.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from src.domain.models import Decision, DecisionState, Side, TraderTrade
from src.domain.params import StrategyParams


@dataclass
class _Run:
    """Mutable accumulator for the current directional run of exposure."""

    wallet: str
    market_id: str
    direction: Side
    opened_at: datetime
    is_reversal: bool = False
    add_shares: Decimal = field(default_factory=lambda: Decimal(0))
    add_cost: Decimal = field(default_factory=lambda: Decimal(0))
    peak: Decimal = field(default_factory=lambda: Decimal(0))
    decision: Decision | None = None


def _dir_price(direction: Side, yes_price: Decimal) -> Decimal:
    """Price of a trade expressed in the run direction's own token, [0, 1]."""
    return yes_price if direction is Side.YES else (Decimal(1) - yes_price)


def build_decisions(
    trades: Iterable[TraderTrade],
    *,
    typical_notional_usd: Decimal,
    params: StrategyParams,
    market_floor_usd: Decimal | None = None,
) -> list[Decision]:
    """Reconstruct independent decisions for a single (wallet, market).

    ``typical_notional_usd`` is the trader's typical position notional, used for
    the fraction-of-typical threshold.

    ``market_floor_usd`` makes the "is this a real decision?" bar **relative to
    the market it happens in** — e.g. the 90th percentile of that market's own
    trade notionals. A flat absolute floor is mis-calibrated across categories:
    in sports ~95% of trades are under $100, so an absolute $100 bar discards the
    entire market rather than its noise. When supplied, it replaces the
    fraction-of-typical rule; ``params.min_notional_usd`` still applies as a hard
    dust guard. All trades must be for the same wallet and market.
    """
    ordered = sorted(trades, key=lambda t: t.timestamp)
    decisions: list[Decision] = []
    net = Decimal(0)
    run: _Run | None = None
    seq = 0

    def try_trigger(active: _Run) -> None:
        nonlocal seq
        if active.decision is not None or active.add_shares <= 0:
            return
        avg = active.add_cost / active.add_shares
        notional = abs(net) * avg
        if market_floor_usd is not None:
            relative_floor = market_floor_usd
        else:
            relative_floor = params.min_fraction_of_typical * typical_notional_usd
        if notional >= params.min_notional_usd and notional >= relative_floor:
            active.decision = Decision(
                wallet=active.wallet,
                market_id=active.market_id,
                direction=active.direction,
                opened_at=active.opened_at,
                entry_price=avg,
                peak_shares=active.peak,
                seq=seq,
                is_reversal=active.is_reversal,
            )
            seq += 1
            decisions.append(active.decision)

    def add_to(active: _Run, price: Decimal, qty: Decimal) -> None:
        active.add_shares += qty
        active.add_cost += price * qty
        active.peak = max(active.peak, abs(net))
        try_trigger(active)
        if active.decision is not None:
            active.decision.entry_price = active.add_cost / active.add_shares
            active.decision.peak_shares = active.peak

    for t in ordered:
        delta = t.yes_delta
        if delta == 0:
            continue
        net += delta

        if run is None:
            # net was 0 before this trade -> open a fresh run
            direction = Side.YES if net > 0 else Side.NO
            run = _Run(t.wallet, t.market_id, direction, t.timestamp)
            add_to(run, _dir_price(direction, t.yes_price), abs(delta))
            continue

        run_positive = run.direction is Side.YES
        delta_positive = delta > 0

        if delta_positive == run_positive:
            # same-direction add
            add_to(run, _dir_price(run.direction, t.yes_price), abs(delta))
        elif net == 0:
            # fully exited before resolution
            if run.decision is not None:
                run.decision.state = DecisionState.CLOSED
                run.decision.closed_at = t.timestamp
            run = None
        elif (net > 0) == run_positive:
            # reduced but still same direction -> decision stays OPEN
            continue
        else:
            # sign flip -> reverse
            had_decision = run.decision is not None
            if had_decision:
                run.decision.state = DecisionState.REVERSED
                run.decision.closed_at = t.timestamp
            new_dir = Side.YES if net > 0 else Side.NO
            run = _Run(
                t.wallet,
                t.market_id,
                new_dir,
                t.timestamp,
                is_reversal=had_decision,
            )
            add_to(run, _dir_price(new_dir, t.yes_price), abs(net))

    return decisions


def decision_correct(decision: Decision, outcome: Side) -> bool | None:
    """Was the decision right at resolution?

    Returns None for decisions not held to resolution (early exits / reversed):
    those belong to the separate early-exit / realized-PnL track, not the
    held-to-resolution win rate.
    """
    if not decision.open_at_resolution:
        return None
    return decision.direction == outcome
