"""End-to-end paper cycle: signal -> risk -> execution -> portfolio -> audit."""

from datetime import datetime
from decimal import Decimal

from src.audit.log import AuditKind, AuditLog
from src.domain.models import Level, Side
from src.domain.params import DEFAULTS
from src.paper.cycle import MarketBooks, process_market
from src.paper.portfolio import PaperPortfolio
from src.signal.engine import MarketQuote, SignalAction, TraderView

T0 = datetime(2026, 1, 1, 12, 0, 0)
FEE = Decimal("0.01")


def views(direction):
    return [
        TraderView("a", direction, 0.9, 50, 1.0, 1.0),
        TraderView("b", direction, 0.9, 50, 1.0, 1.0),
    ]


def quote(yes=0.50, no=0.50, age=60, liq=True):
    return MarketQuote(
        yes_ask=Decimal(str(yes)),
        no_ask=Decimal(str(no)),
        fee_rate=FEE,
        liquidity_ok=liq,
        data_age_sec=age,
        resolution_ambiguous=False,
    )


def books():
    return MarketBooks(
        asks_yes=[Level(Decimal("0.50"), Decimal(1000))],
        bids_yes=[Level(Decimal("0.55"), Decimal(1000))],
        asks_no=[Level(Decimal("0.50"), Decimal(1000))],
        bids_no=[Level(Decimal("0.45"), Decimal(1000))],
        fee_rate=FEE,
    )


def _run(portfolio, audit, v, q):
    return process_market(
        market_id="m1",
        group_id="g1",
        views=v,
        quote=q,
        books=books(),
        portfolio=portfolio,
        audit=audit,
        at=T0,
        detection_at=T0,
        params=DEFAULTS,
    )


def test_buy_opens_position_and_audits():
    p = PaperPortfolio(Decimal(1000))
    audit = AuditLog()
    sig = _run(p, audit, views(Side.YES), quote())
    assert sig.action is SignalAction.BUY_YES
    assert "m1" in p.positions
    # size 3% of 1000 = 30 -> 60 shares @0.50, cost 30.3
    assert p.positions["m1"].shares == Decimal(60)
    assert p.free_balance == Decimal("969.7000")
    kinds = [e.kind for e in audit.events]
    assert AuditKind.SIGNAL in kinds and AuditKind.ENTRY in kinds


def test_no_trade_on_stale_quote_opens_nothing():
    p = PaperPortfolio(Decimal(1000))
    audit = AuditLog()
    sig = _run(p, audit, views(Side.YES), quote(age=400))
    assert sig.action is SignalAction.NO_TRADE
    assert p.positions == {}
    assert any(e.kind is AuditKind.REJECTED for e in audit.events)


def test_exit_closes_when_experts_flip():
    p = PaperPortfolio(Decimal(1000))
    audit = AuditLog()
    _run(p, audit, views(Side.YES), quote())  # open YES
    assert "m1" in p.positions

    sig = _run(p, audit, views(Side.NO), quote(no=0.40))  # experts flip -> exit
    assert sig.action is SignalAction.EXIT
    assert "m1" not in p.positions
    assert any(e.kind is AuditKind.EXIT for e in audit.events)


def test_full_cycle_buy_then_resolve_win():
    p = PaperPortfolio(Decimal(1000))
    audit = AuditLog()
    _run(p, audit, views(Side.YES), quote())
    trade = p.resolve_market("m1", Side.YES, closed_at=T0)
    # 60 shares payoff 60 - cost 30.3 = 29.7
    assert trade.realized_pnl == Decimal("29.7000")
    assert p.positions == {}
