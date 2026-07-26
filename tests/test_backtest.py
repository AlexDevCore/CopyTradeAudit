"""Tests for the leakage-safe backtest harness and its metrics."""

from datetime import timedelta
from decimal import Decimal

from src.backtest.experiments import run_all
from src.backtest.harness import (
    BacktestData,
    MarketMeta,
    TradeRecord,
    as_of_skills,
    market_size_floors,
    select_pool,
)
from src.backtest.metrics import summarize
from src.backtest.synthetic import DT0
from src.domain.models import Action, Side, TraderTrade
from src.domain.params import StrategyParams
from src.normalize.decisions import build_decisions
from src.scoring.skill import TraderSkill


def _trade(wallet, market, ts):
    return TraderTrade.from_token_trade(
        wallet=wallet,
        market_id=market,
        side=Side.YES,
        action=Action.BUY,
        shares=Decimal(500),
        price=Decimal("0.50"),
        timestamp=ts,
    )


def _data():
    markets = {
        "m_past": MarketMeta(
            "m_past", "c", "e_past", Side.YES, DT0 + timedelta(days=1)
        ),
        "m_future": MarketMeta(
            "m_future", "c", "e_future", Side.YES, DT0 + timedelta(days=10)
        ),
    }
    trades = [
        _trade("w1", "m_past", DT0 + timedelta(hours=12)),
        _trade("w1", "m_future", DT0 + timedelta(days=9)),
    ]
    return BacktestData(
        trades=trades, markets=markets, price_fn=lambda *_: Decimal("0.5")
    )


def test_asof_excludes_markets_resolved_after_cutoff():
    data = _data()
    cutoff = DT0 + timedelta(days=5)
    skills = as_of_skills(data, cutoff)
    # only m_past (resolved day 1) counts; m_future (day 10) is invisible
    assert skills[("w1", "c")].n == 1


def test_peeking_would_inflate_the_sample():
    # Using a far-future cutoff (i.e. peeking) sees BOTH markets -> larger n.
    data = _data()
    peek = as_of_skills(data, DT0 + timedelta(days=20))
    assert peek[("w1", "c")].n == 2  # this is exactly the leakage we forbid at t


def test_select_pool_excludes_favourite_buyer():
    skills = {
        ("val", "c"): TraderSkill("val", "c", wins=40, losses=20, mean_roi=0.20),
        ("fav", "c"): TraderSkill("fav", "c", wins=55, losses=5, mean_roi=-0.10),
    }
    pool = select_pool(skills)  # default min_resolved=30, min_mean_roi=0.02
    assert ("val", "c") in pool
    assert ("fav", "c") not in pool  # high win rate, negative edge -> excluded


def test_market_relative_floor_scales_to_the_market():
    # A market of micro-bets: the p90 bar must land near the top of ITS own
    # distribution, not at some absolute dollar figure.
    trades = []
    for i in range(10):
        trades.append(
            TraderTrade.from_token_trade(
                wallet=f"w{i}",
                market_id="cheap",
                side=Side.YES,
                action=Action.BUY,
                shares=Decimal(str((i + 1) * 10)),  # $5 .. $50 notional @0.5
                price=Decimal("0.50"),
                timestamp=DT0,
            )
        )
    floors = market_size_floors(trades, 0.90)
    assert Decimal(40) <= floors["cheap"] <= Decimal(50)


def test_relative_floor_admits_a_big_bet_in_a_micro_market():
    # $30 bet in a market whose trades are ~$5 IS a decision under the relative
    # rule, even though the old absolute $100 floor would have discarded it.
    micro = [
        TraderTrade.from_token_trade(
            wallet="noise",
            market_id="m",
            side=Side.YES,
            action=Action.BUY,
            shares=Decimal(10),
            price=Decimal("0.50"),  # $5
            timestamp=DT0 + timedelta(minutes=i),
        )
        for i in range(20)
    ]
    big = TraderTrade.from_token_trade(
        wallet="whale",
        market_id="m",
        side=Side.YES,
        action=Action.BUY,
        shares=Decimal(60),
        price=Decimal("0.50"),  # $30
        timestamp=DT0 + timedelta(minutes=30),
    )
    floors = market_size_floors(micro + [big], 0.90)
    decs = build_decisions(
        [big],
        typical_notional_usd=Decimal(400),
        params=StrategyParams(),
        market_floor_usd=floors["m"],
    )
    assert len(decs) == 1  # would have been 0 under the old absolute $100 bar


def test_ci_refuses_to_report_on_too_few_events():
    # Two events with identical PnL used to yield a zero-width "significant"
    # interval. That is fake significance; we must refuse instead.
    recs = [_rec("e1", 0.02), _rec("e2", 0.02)]
    m = summarize(recs)
    assert m.ci_low == float("-inf") and m.ci_high == float("inf")
    assert not m.ci_excludes_zero


def _rec(event_id, pnl):
    return TradeRecord(
        market_id=f"m{event_id}",
        event_id=event_id,
        category="c",
        direction=Side.YES,
        entry_price=Decimal("0.5"),
        outcome=Side.YES,
        fee=Decimal(0),
        pnl_per_share=Decimal(str(pnl)),
        detection_at=DT0,
    )


def test_ci_excludes_zero_for_consistent_edge():
    recs = [_rec(f"e{i}", 0.10) for i in range(30)]
    m = summarize(recs)
    assert m.ci_low > 0 and m.ci_excludes_zero


def test_ci_includes_zero_for_symmetric_noise():
    recs = [_rec(f"e{i}", 0.10 if i % 2 else -0.10) for i in range(30)]
    m = summarize(recs)
    assert m.ci_low < 0 < m.ci_high
    assert not m.ci_excludes_zero


def test_event_clustering_widens_ci_vs_naive():
    # Same 20 positive pnls, but all in ONE event -> not enough independent
    # evidence to claim an edge (CI cannot exclude zero).
    one_event = [_rec("only", 0.10) for _ in range(20)]
    assert not summarize(one_event).ci_excludes_zero
    # Spread across 20 events -> real evidence.
    many_events = [_rec(f"e{i}", 0.10) for i in range(20)]
    assert summarize(many_events).ci_excludes_zero


def test_synthetic_recovers_edge_when_inefficient():
    res = run_all(0.3)
    copy = res["copy_strategy"]
    assert copy.mean_pnl_per_share > 0 and copy.ci_low > 0  # EDGE detected


def test_synthetic_reports_null_when_efficient():
    res = run_all(1.0)
    copy = res["copy_strategy"]
    # win rate stays high but there is NO edge -> CI must include zero
    assert not copy.ci_excludes_zero


def test_efficient_market_high_winrate_zero_edge():
    # The point of the whole audit: win rate != profit.
    res = run_all(1.0)
    copy = res["copy_strategy"]
    assert copy.win_rate > 0.6
    assert abs(copy.mean_pnl_per_share) < 0.05


def test_tail_blind_guard_refuses_edge_on_lossless_favourite_book():
    # 12 near-certainty trades, every one a winner: the bootstrap sees no losses
    # and would otherwise report a tight, confident, wrong "EDGE".
    recs = [
        TradeRecord(
            market_id=f"m{i}",
            event_id=f"e{i}",
            category="c",
            direction=Side.YES,
            entry_price=Decimal("0.98"),
            outcome=Side.YES,
            fee=Decimal(0),
            pnl_per_share=Decimal("0.02"),
            detection_at=DT0,
        )
        for i in range(12)
    ]
    m = summarize(recs)
    assert m.win_rate == 1.0
    assert m.ci_low > 0  # the raw interval really is tight and positive
    assert m.tail_blind  # ...but the sample cannot see the -0.98 tail
    assert not m.ci_excludes_zero  # so we refuse to certify an edge


def test_tail_blind_does_not_fire_on_mid_odds_book():
    # Same perfect record at mid odds is not tail-blind: losses there are ordinary.
    recs = [
        TradeRecord(
            market_id=f"m{i}",
            event_id=f"e{i}",
            category="c",
            direction=Side.YES,
            entry_price=Decimal("0.55"),
            outcome=Side.YES,
            fee=Decimal(0),
            pnl_per_share=Decimal("0.45"),
            detection_at=DT0,
        )
        for i in range(12)
    ]
    m = summarize(recs)
    assert not m.tail_blind
    assert m.ci_excludes_zero
