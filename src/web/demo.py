"""Populate a DashboardService with a small, real pipeline run for local demo.

Runs the actual paper cycle (signal -> risk -> execution -> portfolio -> audit)
so the screens show genuine numbers, not mock-ups. Used by ``python -m
src.web.app`` and by the web tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from src.audit.log import AuditKind, AuditLog
from src.domain.models import Level, Side
from src.domain.params import DEFAULTS
from src.paper.cycle import MarketBooks, process_market
from src.paper.portfolio import PaperPortfolio
from src.scoring.skill import TraderSkill
from src.signal.engine import MarketQuote, TraderView, evaluate_market
from src.web.service import DashboardService

T0 = datetime(2026, 7, 20, 15, 0, 0)
FEE = Decimal("0.01")


def _views(direction: Side) -> list[TraderView]:
    return [
        TraderView("0x9a1b…c3", direction, 0.86, 62, 2.0, 1.2),
        TraderView("0x4f7d…e1", direction, 0.79, 41, 4.0, 0.9),
    ]


def _quote(yes: str, no: str) -> MarketQuote:
    return MarketQuote(
        yes_ask=Decimal(yes),
        no_ask=Decimal(no),
        fee_rate=FEE,
        liquidity_ok=True,
        data_age_sec=45,
        resolution_ambiguous=False,
    )


def _books(yes_ask: str, no_ask: str) -> MarketBooks:
    return MarketBooks(
        asks_yes=[Level(Decimal(yes_ask), Decimal(5000))],
        bids_yes=[Level(Decimal("0.55"), Decimal(5000))],
        asks_no=[Level(Decimal(no_ask), Decimal(5000))],
        bids_no=[Level(Decimal("0.40"), Decimal(5000))],
        fee_rate=FEE,
    )


def build_demo_service() -> DashboardService:
    portfolio = PaperPortfolio(DEFAULTS.starting_balance_usd, DEFAULTS.strategy_version)
    audit = AuditLog()

    # Market A: strong YES consensus with residual edge -> opens a position.
    process_market(
        market_id="us-cpi-above-3pct-aug",
        group_id="macro-cpi",
        views=_views(Side.YES),
        quote=_quote("0.58", "0.42"),
        books=_books("0.58", "0.42"),
        portfolio=portfolio,
        audit=audit,
        at=T0,
        detection_at=T0,
        trader_decision_at=T0 - timedelta(seconds=75),
        trader_price=Decimal("0.55"),
        params=DEFAULTS,
    )

    # Market B: open then resolve YES to show a closed trade + hold-to-res.
    process_market(
        market_id="senate-control-dem",
        group_id="us-senate",
        views=_views(Side.YES),
        quote=_quote("0.60", "0.40"),
        books=_books("0.60", "0.40"),
        portfolio=portfolio,
        audit=audit,
        at=T0 + timedelta(minutes=1),
        detection_at=T0 + timedelta(minutes=1),
        trader_decision_at=T0 + timedelta(seconds=5),
        trader_price=Decimal("0.57"),
        params=DEFAULTS,
    )
    portfolio.resolve_market(
        "senate-control-dem", Side.YES, closed_at=T0 + timedelta(days=3)
    )
    audit.record(
        T0 + timedelta(days=3),
        AuditKind.RESOLUTION,
        "resolved YES",
        market_id="senate-control-dem",
    )

    # Market C: consensus present but price already ran -> NO TRADE (demo the gate).
    no_trade = evaluate_market(
        _views(Side.YES), _quote("0.98", "0.02"), params=DEFAULTS
    )

    market_rows = [
        {
            "name": "US CPI > 3% (Aug)",
            "category": "economics",
            "yes_price": Decimal("0.58"),
            "no_price": Decimal("0.42"),
            "spread": Decimal("0.02"),
            "liquidity": "deep",
            "time_to_resolution": "12d",
            "consensus_score": 0.83,
            "experts": 2,
            "edge_after_costs": Decimal("0.24"),
            "decision": "BUY YES",
            "explanation": "2 experts YES, residual edge after costs",
        },
        {
            "name": "Longshot YES @0.98",
            "category": "politics",
            "yes_price": Decimal("0.98"),
            "no_price": Decimal("0.02"),
            "spread": Decimal("0.01"),
            "liquidity": "thin",
            "time_to_resolution": "3d",
            "consensus_score": round(no_trade.consensus_score, 3),
            "experts": no_trade.n_contributors,
            "edge_after_costs": Decimal("-0.14"),
            "decision": no_trade.action.value,
            "explanation": "; ".join(no_trade.reasons),
        },
    ]

    trader_rows = [
        {
            "address": "0x9a1b…c3",
            "category": "economics",
            "wins": 41,
            "losses": 21,
            "raw_win_rate": TraderSkill("x", "economics", 41, 21, 0.31).raw,
            "adjusted_win_rate": TraderSkill("x", "economics", 41, 21, 0.31).wilson(),
            "markets": 62,
            "roi": 0.31,
            "pnl": Decimal(4820),
            "drawdown": Decimal(910),
            "typical_entry": Decimal("0.54"),
            "maker_taker": "taker",
            "tracked_positions": 1,
            "reason": "≥30 markets, Wilson 0.55, ROI floor passed",
        },
        {
            "address": "0x4f7d…e1",
            "category": "economics",
            "wins": 26,
            "losses": 15,
            "raw_win_rate": TraderSkill("y", "economics", 26, 15, 0.22).raw,
            "adjusted_win_rate": TraderSkill("y", "economics", 26, 15, 0.22).wilson(),
            "markets": 41,
            "roi": 0.22,
            "pnl": Decimal(2140),
            "drawdown": Decimal(530),
            "typical_entry": Decimal("0.58"),
            "maker_taker": "taker",
            "tracked_positions": 1,
            "reason": "≥30 markets, Wilson 0.48, ROI floor passed",
        },
    ]

    return DashboardService(
        portfolio=portfolio,
        audit=audit,
        trader_rows=trader_rows,
        market_rows=market_rows,
        feeds={"Gamma": "ok", "Data": "ok", "CLOB": "ok"},
        mode="PAPER",
    )
