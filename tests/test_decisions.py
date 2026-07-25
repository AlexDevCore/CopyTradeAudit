"""Tests for decision reconstruction: the core anti-double-counting logic."""

from datetime import datetime, timedelta
from decimal import Decimal

from src.domain.models import Action, DecisionState, Side, TraderTrade
from src.domain.params import StrategyParams
from src.normalize.decisions import build_decisions, decision_correct

WALLET = "0xabc"
MARKET = "mkt-1"
T0 = datetime(2026, 1, 1, 12, 0, 0)
# typical position $400 -> fraction floor = 0.25 * 400 = $100, same as abs floor
TYPICAL = Decimal(400)
PARAMS = StrategyParams()


def trade(side, action, shares, price, minute):
    return TraderTrade.from_token_trade(
        wallet=WALLET,
        market_id=MARKET,
        side=side,
        action=action,
        shares=Decimal(str(shares)),
        price=Decimal(str(price)),
        timestamp=T0 + timedelta(minutes=minute),
    )


def build(trades):
    return build_decisions(trades, typical_notional_usd=TYPICAL, params=PARAMS)


def test_multiple_same_direction_buys_are_one_decision():
    trades = [
        trade(Side.YES, Action.BUY, 100, 0.50, 0),
        trade(Side.YES, Action.BUY, 100, 0.52, 1),
        trade(Side.YES, Action.BUY, 100, 0.54, 2),
    ]
    decisions = build(trades)
    assert len(decisions) == 1
    d = decisions[0]
    assert d.direction is Side.YES
    assert d.peak_shares == Decimal(300)
    # avg entry = (0.50+0.52+0.54)*100 / 300 = 0.52
    assert d.entry_price == Decimal("0.52")
    assert d.open_at_resolution is True


def test_dust_below_threshold_is_not_a_decision():
    # 10 shares @ 0.50 -> $5 notional, below both floors
    decisions = build([trade(Side.YES, Action.BUY, 10, 0.50, 0)])
    assert decisions == []


def test_reduction_same_direction_stays_open_and_single():
    trades = [
        trade(Side.YES, Action.BUY, 300, 0.50, 0),  # net +300, decision YES
        trade(Side.YES, Action.SELL, 150, 0.60, 1),  # net +150, still YES
    ]
    decisions = build(trades)
    assert len(decisions) == 1
    assert decisions[0].direction is Side.YES
    assert decisions[0].open_at_resolution is True


def test_full_exit_closes_decision_before_resolution():
    trades = [
        trade(Side.YES, Action.BUY, 300, 0.50, 0),
        trade(Side.YES, Action.SELL, 300, 0.60, 1),  # net 0 -> exit
    ]
    decisions = build(trades)
    assert len(decisions) == 1
    assert decisions[0].state is DecisionState.CLOSED
    assert decisions[0].open_at_resolution is False


def test_reversal_creates_second_decision():
    trades = [
        trade(Side.YES, Action.BUY, 300, 0.50, 0),  # net +300 YES
        trade(Side.NO, Action.BUY, 600, 0.50, 1),  # yes_delta -600 -> net -300 NO
    ]
    decisions = build(trades)
    assert len(decisions) == 2
    first, second = decisions
    assert first.direction is Side.YES
    assert first.state is DecisionState.REVERSED
    assert second.direction is Side.NO
    assert second.is_reversal is True
    assert second.open_at_resolution is True


def test_reduction_is_not_counted_as_opposite_prediction():
    # Selling YES down (but not through zero) must not create a NO decision.
    trades = [
        trade(Side.YES, Action.BUY, 400, 0.50, 0),
        trade(Side.YES, Action.SELL, 100, 0.55, 1),
        trade(Side.YES, Action.SELL, 100, 0.58, 2),
    ]
    decisions = build(trades)
    assert len(decisions) == 1
    assert decisions[0].direction is Side.YES


def test_decision_correct_only_scores_held_to_resolution():
    open_yes = build([trade(Side.YES, Action.BUY, 300, 0.50, 0)])[0]
    assert decision_correct(open_yes, Side.YES) is True
    assert decision_correct(open_yes, Side.NO) is False

    exited = build(
        [
            trade(Side.YES, Action.BUY, 300, 0.50, 0),
            trade(Side.YES, Action.SELL, 300, 0.60, 1),
        ]
    )[0]
    # early exit -> not part of held-to-resolution win rate
    assert decision_correct(exited, Side.YES) is None
