"""Thin orchestration of one market evaluation in paper mode.

Ties the deterministic pieces together: signal -> risk -> execution -> portfolio,
logging every branch to the audit trail. Contains no business logic of its own;
each real decision lives in the module it belongs to. Timestamps are supplied by
the caller so the whole cycle replays deterministically.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.audit.log import AuditKind
from src.domain.models import Level, Side
from src.domain.params import DEFAULTS, StrategyParams
from src.paper.execution import simulate_buy, simulate_sell
from src.risk.limits import check_trade
from src.signal.engine import (
    MarketQuote,
    Signal,
    SignalAction,
    TraderView,
    evaluate_market,
)


@dataclass(frozen=True)
class MarketBooks:
    """Execution depth for both tokens of one market, plus its fee rate."""

    asks_yes: Sequence[Level]
    bids_yes: Sequence[Level]
    asks_no: Sequence[Level]
    bids_no: Sequence[Level]
    fee_rate: Decimal


def _prob_for(direction: Side, score: float) -> float:
    return score if direction is Side.YES else 1.0 - score


def process_market(
    *,
    market_id: str,
    group_id: str,
    views: list[TraderView],
    quote: MarketQuote,
    books: MarketBooks,
    portfolio,
    audit,
    at: datetime,
    detection_at: datetime,
    trader_decision_at: datetime | None = None,
    trader_price: Decimal | None = None,
    params: StrategyParams = DEFAULTS,
) -> Signal:
    """Evaluate one market and act on the (gated) signal. Returns the signal."""
    existing = portfolio.positions.get(market_id)
    current_position = existing.direction if existing else None

    signal = evaluate_market(
        views, quote, current_position=current_position, params=params
    )
    audit.record(
        at,
        AuditKind.SIGNAL,
        f"{signal.action.value} score={signal.consensus_score:.3f}",
        market_id=market_id,
        payload={"reasons": list(signal.reasons), "edge": signal.estimated_edge},
    )

    if signal.action is SignalAction.NO_TRADE:
        audit.record(
            at, AuditKind.REJECTED, "; ".join(signal.reasons), market_id=market_id
        )
        return signal

    if signal.action is SignalAction.HOLD:
        return signal

    if signal.action is SignalAction.EXIT:
        bids = books.bids_yes if existing.direction is Side.YES else books.bids_no
        sell = simulate_sell(bids, existing.shares, fee_rate=books.fee_rate)
        trade = portfolio.exit_from_fill(
            market_id, sell, exit_reason="; ".join(signal.reasons), closed_at=at
        )
        audit.record(
            at,
            AuditKind.EXIT,
            f"exit {existing.direction.value} pnl={trade.realized_pnl}",
            market_id=market_id,
            payload={"exit_price": str(sell.avg_price)},
        )
        return signal

    # BUY_YES / BUY_NO
    direction = signal.direction
    group_exposure = portfolio.group_exposure(group_id)
    risk = check_trade(
        portfolio.free_balance, group_exposure, quote.data_age_sec, params
    )
    if not risk.approved:
        audit.record(
            at, AuditKind.REJECTED, f"risk: {risk.reason}", market_id=market_id
        )
        return signal

    asks = books.asks_yes if direction is Side.YES else books.asks_no
    if not asks:
        audit.record(at, AuditKind.REJECTED, "no asks to fill", market_id=market_id)
        return signal

    target_shares = risk.size / asks[0].price
    fill = simulate_buy(asks, target_shares, fee_rate=books.fee_rate)
    if fill.shares_filled <= 0:
        audit.record(at, AuditKind.REJECTED, "empty fill", market_id=market_id)
        return signal

    # Re-check residual edge against the ACTUAL slipped fill price, not top-of-book.
    edge_after_fill = (
        _prob_for(direction, signal.consensus_score)
        - float(fill.avg_price)
        - float(books.fee_rate)
    )
    if edge_after_fill < params.min_edge_after_costs:
        audit.record(
            at,
            AuditKind.REJECTED,
            f"edge gone after slippage ({edge_after_fill:.4f})",
            market_id=market_id,
        )
        return signal

    if fill.total_cost > portfolio.free_balance:
        audit.record(
            at, AuditKind.REJECTED, "cost exceeds free balance", market_id=market_id
        )
        return signal

    position = portfolio.open_from_fill(
        market_id=market_id,
        group_id=group_id,
        direction=direction,
        fill=fill,
        detection_at=detection_at,
        opened_at=at,
        trader_decision_at=trader_decision_at,
        trader_price=trader_price,
        system_price_at_detection=asks[0].price,
        consensus_score=signal.consensus_score,
        contributors=tuple(v.wallet for v in views if v.direction is direction),
        entry_reason="; ".join(signal.reasons),
    )
    audit.record(
        at,
        AuditKind.ENTRY,
        f"buy {direction.value} {position.shares} @ {position.avg_entry_price}",
        market_id=market_id,
        payload={
            "cost_basis": str(position.cost_basis),
            "fee": str(position.entry_fee),
            "slippage": str(position.entry_slippage),
            "edge_after_fill": round(edge_after_fill, 4),
        },
    )
    return signal
