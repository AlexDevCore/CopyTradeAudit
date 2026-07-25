"""Virtual (paper) portfolio.

Money model (Polymarket): buying ``shares`` of a token at avg price ``p`` costs
``shares*p + fee``. At resolution each share pays $1 if that token's outcome
won, else $0. A position is always long the token in its direction.

Every closed trade keeps the full audit record required by the spec, including
both the *actual* exit result and the *hold-to-resolution* counterfactual, so we
can honestly answer "did following exits help or just add lag?".

All cash is Decimal. Serialisable to/from plain dicts for restart safety.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from src.domain.models import Side
from src.paper.execution import Fill

_ZERO = Decimal(0)


def _payoff(direction: Side, outcome: Side, shares: Decimal) -> Decimal:
    """$1/share if the direction token won, else $0."""
    return shares if direction is outcome else _ZERO


@dataclass
class PaperPosition:
    market_id: str
    group_id: str
    direction: Side
    shares: Decimal
    avg_entry_price: Decimal
    cost_basis: Decimal  # cash spent incl. fee
    entry_fee: Decimal
    entry_slippage: Decimal
    opened_at: datetime
    detection_at: datetime
    trader_decision_at: datetime | None
    trader_price: Decimal | None
    system_price_at_detection: Decimal | None
    consensus_score: float
    contributors: tuple[str, ...]
    entry_reason: str
    strategy_version: str
    best_mark: Decimal = field(default=_ZERO)  # highest token price seen
    worst_mark: Decimal = field(default=_ZERO)  # lowest token price seen

    def __post_init__(self) -> None:
        # Initialise excursions at entry price.
        if self.best_mark == _ZERO:
            object.__setattr__(self, "best_mark", self.avg_entry_price)
        if self.worst_mark == _ZERO:
            object.__setattr__(self, "worst_mark", self.avg_entry_price)

    def mark(self, price: Decimal) -> None:
        self.best_mark = max(self.best_mark, price)
        self.worst_mark = min(self.worst_mark, price)

    @property
    def latency_sec(self) -> float | None:
        if self.trader_decision_at is None:
            return None
        return (self.detection_at - self.trader_decision_at).total_seconds()

    @property
    def mfe(self) -> Decimal:
        """Max favourable excursion, in cash (long the direction token)."""
        return (self.best_mark - self.avg_entry_price) * self.shares

    @property
    def mae(self) -> Decimal:
        """Max adverse excursion, in cash."""
        return (self.worst_mark - self.avg_entry_price) * self.shares

    def value_at(self, price: Decimal) -> Decimal:
        return self.shares * price


@dataclass
class ClosedTrade:
    market_id: str
    group_id: str
    direction: Side
    shares: Decimal
    avg_entry_price: Decimal
    cost_basis: Decimal
    entry_fee: Decimal
    entry_slippage: Decimal
    opened_at: datetime
    detection_at: datetime
    trader_decision_at: datetime | None
    trader_price: Decimal | None
    system_price_at_detection: Decimal | None
    consensus_score: float
    contributors: tuple[str, ...]
    entry_reason: str
    strategy_version: str
    closed_at: datetime
    exit_reason: str
    exit_price: Decimal | None  # avg sell price; None if settled at resolution
    exit_fee: Decimal
    realized_pnl: Decimal
    mfe: Decimal
    mae: Decimal
    outcome: Side | None = None
    hold_to_resolution_pnl: Decimal | None = None

    @property
    def latency_sec(self) -> float | None:
        if self.trader_decision_at is None:
            return None
        return (self.detection_at - self.trader_decision_at).total_seconds()


class PaperPortfolio:
    """One position per market (MVP). Deterministic, no I/O."""

    def __init__(
        self, starting_balance: Decimal, strategy_version: str = "v0.0"
    ) -> None:
        self.starting_balance = starting_balance
        self.free_balance = starting_balance
        self.strategy_version = strategy_version
        self.positions: dict[str, PaperPosition] = {}
        self.closed: list[ClosedTrade] = []
        self._peak_equity = starting_balance
        self._max_drawdown = _ZERO

    # --- opening / marking --------------------------------------------------

    def open_from_fill(
        self,
        *,
        market_id: str,
        group_id: str,
        direction: Side,
        fill: Fill,
        detection_at: datetime,
        opened_at: datetime,
        trader_decision_at: datetime | None = None,
        trader_price: Decimal | None = None,
        system_price_at_detection: Decimal | None = None,
        consensus_score: float,
        contributors: tuple[str, ...],
        entry_reason: str,
    ) -> PaperPosition:
        if market_id in self.positions:
            raise ValueError(f"position already open for {market_id}")
        if fill.shares_filled <= 0:
            raise ValueError("cannot open a position from an empty fill")
        if fill.total_cost > self.free_balance:
            raise ValueError("insufficient free balance for this fill")

        position = PaperPosition(
            market_id=market_id,
            group_id=group_id,
            direction=direction,
            shares=fill.shares_filled,
            avg_entry_price=fill.avg_price,
            cost_basis=fill.total_cost,
            entry_fee=fill.fee,
            entry_slippage=fill.slippage,
            opened_at=opened_at,
            detection_at=detection_at,
            trader_decision_at=trader_decision_at,
            trader_price=trader_price,
            system_price_at_detection=system_price_at_detection,
            consensus_score=consensus_score,
            contributors=contributors,
            entry_reason=entry_reason,
            strategy_version=self.strategy_version,
        )
        self.free_balance -= fill.total_cost
        self.positions[market_id] = position
        return position

    def mark(self, market_id: str, price: Decimal) -> None:
        pos = self.positions.get(market_id)
        if pos is not None:
            pos.mark(price)

    def group_exposure(self, group_id: str) -> Decimal:
        """Cash cost basis currently deployed in one correlated group."""
        return sum(
            (p.cost_basis for p in self.positions.values() if p.group_id == group_id),
            _ZERO,
        )

    # --- closing ------------------------------------------------------------

    def exit_from_fill(
        self, market_id: str, sell: Fill, *, exit_reason: str, closed_at: datetime
    ) -> ClosedTrade:
        pos = self.positions.pop(market_id)
        proceeds = sell.notional - sell.fee
        self.free_balance += proceeds
        realized = proceeds - pos.cost_basis
        trade = self._to_closed(
            pos,
            closed_at=closed_at,
            exit_reason=exit_reason,
            exit_price=sell.avg_price,
            exit_fee=sell.fee,
            realized_pnl=realized,
        )
        # hold_to_resolution_pnl stays None until the market resolves.
        self.closed.append(trade)
        return trade

    def resolve_market(
        self, market_id: str, outcome: Side, *, closed_at: datetime
    ) -> ClosedTrade | None:
        """Settle any open position at resolution and backfill counterfactuals.

        For a still-open position: pay out and record it (its hold-to-resolution
        result equals its realized result, since it was held). For any position
        in this market that exited early, fill in what holding would have paid.
        """
        settled: ClosedTrade | None = None
        pos = self.positions.pop(market_id, None)
        if pos is not None:
            payoff = _payoff(pos.direction, outcome, pos.shares)
            self.free_balance += payoff
            realized = payoff - pos.cost_basis
            settled = self._to_closed(
                pos,
                closed_at=closed_at,
                exit_reason="resolution",
                exit_price=None,
                exit_fee=_ZERO,
                realized_pnl=realized,
            )
            settled.outcome = outcome
            settled.hold_to_resolution_pnl = realized
            self.closed.append(settled)

        for trade in self.closed:
            if (
                trade.market_id == market_id
                and trade.exit_reason != "resolution"
                and trade.hold_to_resolution_pnl is None
            ):
                payoff = _payoff(trade.direction, outcome, trade.shares)
                trade.outcome = outcome
                trade.hold_to_resolution_pnl = payoff - trade.cost_basis
        return settled

    def _to_closed(
        self,
        pos: PaperPosition,
        *,
        closed_at: datetime,
        exit_reason: str,
        exit_price: Decimal | None,
        exit_fee: Decimal,
        realized_pnl: Decimal,
    ) -> ClosedTrade:
        return ClosedTrade(
            market_id=pos.market_id,
            group_id=pos.group_id,
            direction=pos.direction,
            shares=pos.shares,
            avg_entry_price=pos.avg_entry_price,
            cost_basis=pos.cost_basis,
            entry_fee=pos.entry_fee,
            entry_slippage=pos.entry_slippage,
            opened_at=pos.opened_at,
            detection_at=pos.detection_at,
            trader_decision_at=pos.trader_decision_at,
            trader_price=pos.trader_price,
            system_price_at_detection=pos.system_price_at_detection,
            consensus_score=pos.consensus_score,
            contributors=pos.contributors,
            entry_reason=pos.entry_reason,
            strategy_version=pos.strategy_version,
            closed_at=closed_at,
            exit_reason=exit_reason,
            exit_price=exit_price,
            exit_fee=exit_fee,
            realized_pnl=realized_pnl,
            mfe=pos.mfe,
            mae=pos.mae,
        )

    # --- metrics ------------------------------------------------------------

    @property
    def realized_pnl(self) -> Decimal:
        return sum((t.realized_pnl for t in self.closed), _ZERO)

    def unrealized_pnl(self, marks: dict[str, Decimal]) -> Decimal:
        total = _ZERO
        for pos in self.positions.values():
            price = marks.get(pos.market_id, pos.avg_entry_price)
            total += pos.value_at(price) - pos.cost_basis
        return total

    def open_value(self, marks: dict[str, Decimal]) -> Decimal:
        return sum(
            (
                p.value_at(marks.get(p.market_id, p.avg_entry_price))
                for p in self.positions.values()
            ),
            _ZERO,
        )

    def equity(self, marks: dict[str, Decimal]) -> Decimal:
        equity = self.free_balance + self.open_value(marks)
        self._record_equity(equity)
        return equity

    def _record_equity(self, equity: Decimal) -> None:
        self._peak_equity = max(self._peak_equity, equity)
        drawdown = self._peak_equity - equity
        self._max_drawdown = max(self._max_drawdown, drawdown)

    @property
    def max_drawdown(self) -> Decimal:
        return self._max_drawdown
