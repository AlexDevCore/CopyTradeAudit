"""Tests for win-rate statistics and decision-based scoring."""

from datetime import datetime, timedelta
from decimal import Decimal

from src.domain.models import Action, Side, TraderTrade
from src.domain.params import StrategyParams
from src.normalize.decisions import build_decisions
from src.scoring.winrate import (
    TraderScore,
    raw_win_rate,
    score_from_decisions,
    wilson_lower_bound,
)


def test_raw_win_rate_basic():
    assert raw_win_rate(9, 10) == 0.9
    assert raw_win_rate(0, 0) == 0.0


def test_wilson_empty_sample_is_zero():
    assert wilson_lower_bound(0, 0) == 0.0


def test_wilson_lower_bound_below_raw():
    # Lower bound must be strictly below the point estimate for a real sample.
    assert wilson_lower_bound(9, 10) < 0.9


def test_small_lucky_sample_ranks_below_large_solid_one():
    # 9/10 (raw 0.90) must NOT outrank 160/200 (raw 0.80) once adjusted.
    small = wilson_lower_bound(9, 10)
    large = wilson_lower_bound(160, 200)
    assert small < large


def test_more_evidence_raises_lower_bound_at_same_rate():
    # Same 80% hit rate, more samples -> higher (more trustworthy) lower bound.
    assert wilson_lower_bound(8, 10) < wilson_lower_bound(80, 100)


def test_trader_score_properties():
    score = TraderScore(wallet="0x1", category="politics", wins=160, losses=40)
    assert score.n == 200
    assert score.raw == 0.8
    assert 0.0 < score.wilson() < 0.8


def _decision(market, side, minute):
    t0 = datetime(2026, 1, 1)
    trade = TraderTrade.from_token_trade(
        wallet="0x1",
        market_id=market,
        side=side,
        action=Action.BUY,
        shares=Decimal(300),
        price=Decimal("0.50"),
        timestamp=t0 + timedelta(minutes=minute),
    )
    return build_decisions(
        [trade], typical_notional_usd=Decimal(400), params=StrategyParams()
    )[0]


def test_score_from_decisions_counts_only_resolved():
    decisions = [
        _decision("m1", Side.YES, 0),  # outcome YES -> win
        _decision("m2", Side.NO, 1),  # outcome NO  -> win
        _decision("m3", Side.YES, 2),  # outcome NO  -> loss
        _decision("m4", Side.YES, 3),  # unresolved  -> skipped
    ]
    outcomes = {"m1": Side.YES, "m2": Side.NO, "m3": Side.NO}
    score = score_from_decisions("0x1", "politics", decisions, outcomes)
    assert score.wins == 2
    assert score.losses == 1
    assert score.n == 3
