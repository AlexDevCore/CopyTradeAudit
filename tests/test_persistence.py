"""Restart safety: portfolio + audit survive a store round-trip."""

import json
from datetime import datetime
from decimal import Decimal

from src.audit.log import AuditKind, AuditLog
from src.domain.models import Level, Side
from src.paper.execution import simulate_buy
from src.paper.portfolio import PaperPortfolio
from src.paper.serialize import portfolio_from_dict, portfolio_to_dict
from src.store.db import Store

T0 = datetime(2026, 1, 1, 12, 0, 0)
FEE = Decimal("0.01")


def _portfolio_with_activity():
    p = PaperPortfolio(Decimal(1000), strategy_version="v1.0")
    fill = simulate_buy(
        [Level(Decimal("0.50"), Decimal(1000))], Decimal(100), fee_rate=FEE
    )
    p.open_from_fill(
        market_id="open1",
        group_id="g1",
        direction=Side.YES,
        fill=fill,
        detection_at=T0,
        opened_at=T0,
        consensus_score=0.9,
        contributors=("0xA",),
        entry_reason="entry",
    )
    fill2 = simulate_buy(
        [Level(Decimal("0.40"), Decimal(1000))], Decimal(50), fee_rate=FEE
    )
    p.open_from_fill(
        market_id="closed1",
        group_id="g2",
        direction=Side.NO,
        fill=fill2,
        detection_at=T0,
        opened_at=T0,
        consensus_score=0.8,
        contributors=("0xB",),
        entry_reason="entry2",
    )
    p.resolve_market("closed1", Side.NO, closed_at=T0)
    return p


def test_portfolio_dict_round_trip():
    p = _portfolio_with_activity()
    restored = portfolio_from_dict(portfolio_to_dict(p))
    assert restored.free_balance == p.free_balance
    assert set(restored.positions) == set(p.positions)
    assert restored.positions["open1"].shares == p.positions["open1"].shares
    assert len(restored.closed) == len(p.closed)
    assert restored.closed[0].realized_pnl == p.closed[0].realized_pnl


def test_portfolio_survives_store_restart(tmp_path):
    db = tmp_path / "state.db"
    p = _portfolio_with_activity()

    store = Store(db)
    store.set_state("portfolio", json.dumps(portfolio_to_dict(p)))
    store.close()

    reopened = Store(db)
    restored = portfolio_from_dict(json.loads(reopened.get_state("portfolio")))
    reopened.close()

    assert restored.free_balance == p.free_balance
    assert restored.positions["open1"].direction is Side.YES
    assert restored.closed[0].market_id == "closed1"


def test_audit_events_persist(tmp_path):
    db = tmp_path / "audit.db"
    store = Store(db)
    log = AuditLog(store)
    log.record(T0, AuditKind.SIGNAL, "signal a", market_id="m1")
    log.record(T0, AuditKind.ENTRY, "entry a", market_id="m1", payload={"x": 1})
    store.close()

    reopened = Store(db)
    rows = list(reopened.iter_audit_events())
    reopened.close()
    assert [r["kind"] for r in rows] == ["SIGNAL", "ENTRY"]
    assert json.loads(rows[1]["payload_json"]) == {"x": 1}
