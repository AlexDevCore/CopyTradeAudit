"""Dashboard view-model layer.

Pure: turns portfolio / audit / trader / market state into plain dict + list
structures. No HTTP, no HTML — so every number shown on a screen is unit
testable. The web layer only renders what this returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from src.audit.log import AuditLog
from src.paper.portfolio import PaperPortfolio

_ZERO = Decimal(0)


@dataclass
class DashboardService:
    portfolio: PaperPortfolio
    audit: AuditLog
    trader_rows: list[dict[str, Any]] = field(default_factory=list)
    market_rows: list[dict[str, Any]] = field(default_factory=list)
    marks: dict[str, Decimal] = field(default_factory=dict)
    feeds: dict[str, str] = field(default_factory=dict)
    mode: str = "PAPER"  # never defaults to LIVE

    # --- 1. Dashboard -------------------------------------------------------

    def dashboard(self) -> dict[str, Any]:
        p = self.portfolio
        open_value = p.open_value(self.marks)
        unrealized = p.unrealized_pnl(self.marks)
        realized = p.realized_pnl
        equity = p.equity(self.marks)  # also refreshes drawdown
        resolved = [t for t in p.closed if t.outcome is not None]
        wins = sum(1 for t in resolved if t.realized_pnl > 0)
        win_rate = wins / len(resolved) if resolved else None
        return {
            "mode": self.mode,
            "starting_balance": p.starting_balance,
            "free_balance": p.free_balance,
            "open_value": open_value,
            "open_positions": len(p.positions),
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "equity": equity,
            "net_result": equity - p.starting_balance,  # after all costs
            "max_drawdown": p.max_drawdown,
            "strategy_win_rate": win_rate,
            "resolved_trades": len(resolved),
            "feeds": self.feeds,
        }

    # --- 2. Markets ---------------------------------------------------------

    def markets(self) -> list[dict[str, Any]]:
        return self.market_rows

    # --- 3. Traders ---------------------------------------------------------

    def traders(self) -> list[dict[str, Any]]:
        return self.trader_rows

    # --- 4. Paper portfolio -------------------------------------------------

    def portfolio_view(self) -> dict[str, list[dict[str, Any]]]:
        open_rows = [
            {
                "market_id": pos.market_id,
                "direction": pos.direction.value,
                "shares": pos.shares,
                "avg_entry_price": pos.avg_entry_price,
                "cost_basis": pos.cost_basis,
                "fee": pos.entry_fee,
                "slippage": pos.entry_slippage,
                "consensus_score": pos.consensus_score,
                "entry_reason": pos.entry_reason,
            }
            for pos in self.portfolio.positions.values()
        ]
        closed_rows = [
            {
                "market_id": t.market_id,
                "direction": t.direction.value,
                "outcome": t.outcome.value if t.outcome else "—",
                "shares": t.shares,
                "signal_price": t.system_price_at_detection,
                "fill_price": t.avg_entry_price,
                "trader_price": t.trader_price,
                "fee": t.entry_fee,
                "slippage": t.entry_slippage,
                "latency_sec": t.latency_sec,
                "realized_pnl": t.realized_pnl,
                "hold_to_resolution_pnl": t.hold_to_resolution_pnl,
                "entry_reason": t.entry_reason,
                "exit_reason": t.exit_reason,
            }
            for t in self.portfolio.closed
        ]
        return {"open": open_rows, "closed": closed_rows}

    # --- 5. Audit log -------------------------------------------------------

    def audit_view(self) -> list[dict[str, Any]]:
        return [
            {
                "at": e.at.isoformat(),
                "kind": e.kind.value,
                "market_id": e.market_id or "—",
                "message": e.message,
            }
            for e in self.audit.events
        ]
