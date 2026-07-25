"""Tests for the paper portfolio: PnL, exit-vs-hold, drawdown, excursions."""

from datetime import datetime
from decimal import Decimal

from src.domain.models import Level, Side
from src.paper.execution import simulate_buy, simulate_sell
from src.paper.portfolio import PaperPortfolio

T0 = datetime(2026, 1, 1, 12, 0, 0)
FEE = Decimal("0.01")


def _open_yes(portfolio, market="m1", group="g1"):
    fill = simulate_buy(
        [Level(Decimal("0.50"), Decimal(1000))], Decimal(100), fee_rate=FEE
    )
    return portfolio.open_from_fill(
        market_id=market,
        group_id=group,
        direction=Side.YES,
        fill=fill,
        detection_at=T0,
        opened_at=T0,
        consensus_score=0.9,
        contributors=("0xA",),
        entry_reason="test entry",
    )


def test_open_deducts_cost_from_balance():
    p = PaperPortfolio(Decimal(1000))
    pos = _open_yes(p)
    # cost basis = 100 * 0.50 + fee 0.5 = 50.5
    assert pos.cost_basis == Decimal("50.5000")
    assert p.free_balance == Decimal("949.5000")


def test_resolve_win_pays_out():
    p = PaperPortfolio(Decimal(1000))
    _open_yes(p)
    trade = p.resolve_market("m1", Side.YES, closed_at=T0)
    # payoff 100 - cost 50.5 = 49.5
    assert trade.realized_pnl == Decimal("49.5000")
    assert trade.hold_to_resolution_pnl == Decimal("49.5000")
    assert p.free_balance == Decimal("1049.5000")


def test_resolve_loss():
    p = PaperPortfolio(Decimal(1000))
    _open_yes(p)
    trade = p.resolve_market("m1", Side.NO, closed_at=T0)
    assert trade.realized_pnl == Decimal("-50.5000")


def test_early_exit_vs_hold_to_resolution_comparison():
    p = PaperPortfolio(Decimal(1000))
    _open_yes(p)
    # exit early at 0.60
    sell = simulate_sell(
        [Level(Decimal("0.60"), Decimal(1000))], Decimal(100), fee_rate=FEE
    )
    trade = p.exit_from_fill("m1", sell, exit_reason="rule exit", closed_at=T0)
    # proceeds 60 - fee 0.6 = 59.4 ; realized = 59.4 - 50.5 = 8.9
    assert trade.realized_pnl == Decimal("8.9000")
    assert trade.hold_to_resolution_pnl is None

    # market later resolves YES -> holding would have paid 49.5
    p.resolve_market("m1", Side.YES, closed_at=T0)
    assert trade.hold_to_resolution_pnl == Decimal("49.5000")
    # This is the whole point: exiting early (8.9) underperformed holding (49.5).
    assert trade.realized_pnl < trade.hold_to_resolution_pnl


def test_group_exposure_and_drawdown():
    p = PaperPortfolio(Decimal(1000))
    _open_yes(p, market="m1", group="g1")
    assert p.group_exposure("g1") == Decimal("50.5000")

    # mark the position down -> drawdown grows
    p.mark("m1", Decimal("0.30"))
    equity = p.equity({"m1": Decimal("0.30")})
    # equity = free 949.5 + 100*0.30 = 979.5 ; peak 1000 -> dd 20.5
    assert equity == Decimal("979.5000")
    assert p.max_drawdown == Decimal("20.5000")


def test_mfe_mae_track_excursions():
    p = PaperPortfolio(Decimal(1000))
    pos = _open_yes(p)
    p.mark("m1", Decimal("0.65"))
    p.mark("m1", Decimal("0.40"))
    assert pos.mfe == Decimal("15.00")  # (0.65-0.50)*100
    assert pos.mae == Decimal("-10.00")  # (0.40-0.50)*100
