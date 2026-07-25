"""Tests for the signal engine: consensus + residual edge + NO TRADE gate."""

from decimal import Decimal

from src.domain.models import Side
from src.signal.engine import (
    MarketQuote,
    SignalAction,
    TraderView,
    consensus,
    evaluate_market,
)


def view(wallet, direction, skill=0.9, n=50, freshness=1.0, size=1.0, indep=1.0):
    return TraderView(wallet, direction, skill, n, freshness, size, indep)


def quote(yes=0.60, no=0.40, fee=0.01, liq=True, age=60, ambiguous=False):
    return MarketQuote(
        yes_ask=Decimal(str(yes)),
        no_ask=Decimal(str(no)),
        fee_rate=Decimal(str(fee)),
        liquidity_ok=liq,
        data_age_sec=age,
        resolution_ambiguous=ambiguous,
    )


def test_consensus_leans_toward_agreeing_experts():
    score, total = consensus([view("a", Side.YES), view("b", Side.YES)])
    assert score > 0.9
    assert total > 0
    # Opposing equal-weight experts cancel to neutral.
    score2, _ = consensus([view("a", Side.YES), view("b", Side.NO)])
    assert abs(score2 - 0.5) < 1e-9


def test_strong_consensus_with_edge_is_a_buy():
    sig = evaluate_market([view("a", Side.YES), view("b", Side.YES)], quote())
    assert sig.action is SignalAction.BUY_YES
    assert sig.direction is Side.YES
    assert sig.estimated_edge is not None and sig.estimated_edge > 0.02


def test_no_trade_on_stale_data():
    sig = evaluate_market([view("a", Side.YES), view("b", Side.YES)], quote(age=400))
    assert sig.action is SignalAction.NO_TRADE
    assert "stale" in sig.reasons[0]


def test_no_trade_when_too_few_experts():
    sig = evaluate_market([view("a", Side.YES)], quote())
    assert sig.action is SignalAction.NO_TRADE


def test_no_trade_when_experts_contradict():
    sig = evaluate_market([view("a", Side.YES), view("b", Side.NO)], quote())
    assert sig.action is SignalAction.NO_TRADE
    assert any("contradict" in r for r in sig.reasons)


def test_no_trade_when_edge_gone_after_costs():
    # Price already at 0.98 -> residual edge negative.
    sig = evaluate_market([view("a", Side.YES), view("b", Side.YES)], quote(yes=0.98))
    assert sig.action is SignalAction.NO_TRADE
    assert any("edge gone" in r for r in sig.reasons)


def test_no_trade_when_liquidity_insufficient():
    sig = evaluate_market([view("a", Side.YES), view("b", Side.YES)], quote(liq=False))
    assert sig.action is SignalAction.NO_TRADE
    assert any("liquidity" in r for r in sig.reasons)


def test_hold_when_position_matches_direction():
    sig = evaluate_market(
        [view("a", Side.YES), view("b", Side.YES)], quote(), current_position=Side.YES
    )
    assert sig.action is SignalAction.HOLD


def test_exit_when_experts_flip_against_position():
    sig = evaluate_market(
        [view("a", Side.YES), view("b", Side.YES)], quote(), current_position=Side.NO
    )
    assert sig.action is SignalAction.EXIT
