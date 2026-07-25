"""Build an explainable signal for one market and gate it hard toward NO TRADE.

Two deliberate design choices from the spec:

  * Not a naive vote. Each contributing trader's directional exposure is weighted
    by price-aware skill, evidence (shrinkage on decision count), freshness, and
    conviction (size vs typical), then down-weighted for correlation. The result
    is a ``consensus_score`` in [0, 1] — provisional, NOT a calibrated
    probability, until we have enough history to calibrate.

  * Residual edge, not the trader's edge (fix b). Edge is computed against the
    price *available to us at detection* (effective fill price incl. slippage)
    minus fees — never the trader's price. If the move has already priced the
    signal in, the edge is gone and we do not trade.

Any missing condition returns NO_TRADE with an explicit reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from src.domain.models import Side
from src.domain.params import DEFAULTS, StrategyParams


class SignalAction(str, Enum):
    BUY_YES = "BUY_YES"
    BUY_NO = "BUY_NO"
    HOLD = "HOLD"
    EXIT = "EXIT"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class TraderView:
    """A tracked trader's current stance in one market."""

    wallet: str
    direction: Side  # sign of current net exposure in THIS market
    skill: float  # price-aware skill in [0, 1] (0.5 == no edge)
    n_decisions: int  # resolved decisions behind the skill estimate
    freshness_days: float  # days since the trader's last decision
    size_ratio: float  # current position size / trader's typical size
    independence: float = 1.0  # [0, 1] down-weight for correlated wallets


@dataclass(frozen=True)
class MarketQuote:
    """What execution/liquidity looks like to us right now for a unit trade."""

    yes_ask: Decimal  # effective price to BUY YES (incl. slippage)
    no_ask: Decimal  # effective price to BUY NO (incl. slippage)
    fee_rate: Decimal  # per-market, fetched (never hard-coded)
    liquidity_ok: bool  # target size was fully fillable
    data_age_sec: int  # age of the freshest input driving this quote
    resolution_ambiguous: bool = False


@dataclass(frozen=True)
class Signal:
    action: SignalAction
    direction: Side | None
    consensus_score: float  # [0, 1], > 0.5 leans YES (provisional)
    n_contributors: int
    estimated_edge: float | None  # residual edge after costs, or None
    reasons: tuple[str, ...]

    @property
    def is_trade(self) -> bool:
        return self.action in (SignalAction.BUY_YES, SignalAction.BUY_NO)


def _view_weight(view: TraderView, params: StrategyParams) -> float:
    """Non-negative weight of one trader's view."""
    skill_w = max(0.0, view.skill - 0.5) * 2.0
    evidence_w = view.n_decisions / (view.n_decisions + params.evidence_shrinkage_k)
    freshness_w = math.exp(-max(0.0, view.freshness_days) / params.freshness_tau_days)
    conviction_w = 0.5 + min(max(view.size_ratio, 0.0), 2.0) / 2.0
    independence = max(0.0, min(1.0, view.independence))
    return skill_w * evidence_w * freshness_w * conviction_w * independence


def _positive_weighted(
    views: list[TraderView], params: StrategyParams
) -> list[tuple[TraderView, float]]:
    """Weight each view once, keep the contributing ones, in a fixed order."""
    weighted = [(v, _view_weight(v, params)) for v in views]
    positive = [(v, w) for v, w in weighted if w > 0.0]
    positive.sort(key=lambda pair: pair[0].wallet)  # determinism
    return positive


def _score(weighted: list[tuple[TraderView, float]]) -> tuple[float, float]:
    """Reduce pre-weighted views to (consensus_score in [0,1], total_weight)."""
    total_w = 0.0
    signed = 0.0
    for view, weight in weighted:
        total_w += weight
        signed += weight * (1.0 if view.direction is Side.YES else -1.0)
    if total_w <= 0.0:
        return 0.5, 0.0
    return (signed / total_w + 1.0) / 2.0, total_w


def consensus(
    views: list[TraderView], params: StrategyParams = DEFAULTS
) -> tuple[float, float]:
    """Return (consensus_score in [0,1], total_weight)."""
    return _score(_positive_weighted(views, params))


def evaluate_market(
    views: list[TraderView],
    quote: MarketQuote,
    *,
    current_position: Side | None = None,
    params: StrategyParams = DEFAULTS,
) -> Signal:
    """Produce a gated, explainable signal for one market."""
    reasons: list[str] = []

    def no_trade(reason: str, score: float = 0.5, n: int = 0) -> Signal:
        return Signal(SignalAction.NO_TRADE, None, score, n, None, (reason,))

    if quote.data_age_sec > params.data_staleness_sec:
        return no_trade(
            f"stale data ({quote.data_age_sec}s > {params.data_staleness_sec}s)"
        )
    if quote.resolution_ambiguous:
        return no_trade("resolution rules ambiguous")

    weighted = _positive_weighted(views, params)  # weights computed once
    n = len(weighted)
    if n < params.min_signal_contributors:
        return no_trade(
            f"too few experts ({n} < {params.min_signal_contributors})", n=n
        )

    score, total_w = _score(weighted)
    if total_w <= 0.0:
        return no_trade("no weighted expert support", score, n)

    direction = Side.YES if score >= 0.5 else Side.NO
    # Decisive if the score clears the threshold on the leaning side.
    decisive = score >= params.consensus_threshold or score <= (
        1.0 - params.consensus_threshold
    )
    if not decisive:
        reasons.append(f"experts contradict (score {score:.3f})")
        return Signal(SignalAction.NO_TRADE, direction, score, n, None, tuple(reasons))

    if not quote.liquidity_ok:
        reasons.append("insufficient liquidity for target size")
        return Signal(SignalAction.NO_TRADE, direction, score, n, None, tuple(reasons))

    # Residual edge vs the price available to US, minus fees (fix b).
    if direction is Side.YES:
        prob = score
        price = float(quote.yes_ask)
    else:
        prob = 1.0 - score
        price = float(quote.no_ask)
    edge = prob - price - float(quote.fee_rate)

    if edge < params.min_edge_after_costs:
        reasons.append(
            f"edge gone after costs (edge {edge:.4f} < {params.min_edge_after_costs})"
        )
        return Signal(SignalAction.NO_TRADE, direction, score, n, edge, tuple(reasons))

    reasons.append(f"consensus {score:.3f} ({n} experts), residual edge {edge:.4f}")

    # Position-aware action.
    if current_position is None:
        action = SignalAction.BUY_YES if direction is Side.YES else SignalAction.BUY_NO
    elif current_position is direction:
        action = SignalAction.HOLD
        reasons.append("holding: experts still favour current direction")
    else:
        action = SignalAction.EXIT
        reasons.append("exit: experts decisively flipped against current position")

    return Signal(action, direction, score, n, edge, tuple(reasons))
