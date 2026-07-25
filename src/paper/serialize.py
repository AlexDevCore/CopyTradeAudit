"""Serialise a PaperPortfolio to/from plain dicts (JSON-friendly) for restart.

Kept separate from the portfolio logic so the domain object stays free of
persistence concerns. Decimals become strings, datetimes ISO 8601, Side its
value — round-tripping is exact.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.domain.models import Side
from src.paper.portfolio import ClosedTrade, PaperPortfolio, PaperPosition


def _dec(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _dt(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _side(value: Side | None) -> str | None:
    return None if value is None else value.value


def _position_to_dict(pos: PaperPosition) -> dict[str, Any]:
    return {
        "market_id": pos.market_id,
        "group_id": pos.group_id,
        "direction": pos.direction.value,
        "shares": _dec(pos.shares),
        "avg_entry_price": _dec(pos.avg_entry_price),
        "cost_basis": _dec(pos.cost_basis),
        "entry_fee": _dec(pos.entry_fee),
        "entry_slippage": _dec(pos.entry_slippage),
        "opened_at": _dt(pos.opened_at),
        "detection_at": _dt(pos.detection_at),
        "trader_decision_at": _dt(pos.trader_decision_at),
        "trader_price": _dec(pos.trader_price),
        "system_price_at_detection": _dec(pos.system_price_at_detection),
        "consensus_score": pos.consensus_score,
        "contributors": list(pos.contributors),
        "entry_reason": pos.entry_reason,
        "strategy_version": pos.strategy_version,
        "best_mark": _dec(pos.best_mark),
        "worst_mark": _dec(pos.worst_mark),
    }


def _position_from_dict(data: dict[str, Any]) -> PaperPosition:
    return PaperPosition(
        market_id=data["market_id"],
        group_id=data["group_id"],
        direction=Side(data["direction"]),
        shares=Decimal(data["shares"]),
        avg_entry_price=Decimal(data["avg_entry_price"]),
        cost_basis=Decimal(data["cost_basis"]),
        entry_fee=Decimal(data["entry_fee"]),
        entry_slippage=Decimal(data["entry_slippage"]),
        opened_at=datetime.fromisoformat(data["opened_at"]),
        detection_at=datetime.fromisoformat(data["detection_at"]),
        trader_decision_at=(
            datetime.fromisoformat(data["trader_decision_at"])
            if data["trader_decision_at"]
            else None
        ),
        trader_price=(
            Decimal(data["trader_price"]) if data["trader_price"] is not None else None
        ),
        system_price_at_detection=(
            Decimal(data["system_price_at_detection"])
            if data["system_price_at_detection"] is not None
            else None
        ),
        consensus_score=data["consensus_score"],
        contributors=tuple(data["contributors"]),
        entry_reason=data["entry_reason"],
        strategy_version=data["strategy_version"],
        best_mark=Decimal(data["best_mark"]),
        worst_mark=Decimal(data["worst_mark"]),
    )


def _closed_to_dict(trade: ClosedTrade) -> dict[str, Any]:
    return {
        "market_id": trade.market_id,
        "group_id": trade.group_id,
        "direction": trade.direction.value,
        "shares": _dec(trade.shares),
        "avg_entry_price": _dec(trade.avg_entry_price),
        "cost_basis": _dec(trade.cost_basis),
        "entry_fee": _dec(trade.entry_fee),
        "entry_slippage": _dec(trade.entry_slippage),
        "opened_at": _dt(trade.opened_at),
        "detection_at": _dt(trade.detection_at),
        "trader_decision_at": _dt(trade.trader_decision_at),
        "trader_price": _dec(trade.trader_price),
        "system_price_at_detection": _dec(trade.system_price_at_detection),
        "consensus_score": trade.consensus_score,
        "contributors": list(trade.contributors),
        "entry_reason": trade.entry_reason,
        "strategy_version": trade.strategy_version,
        "closed_at": _dt(trade.closed_at),
        "exit_reason": trade.exit_reason,
        "exit_price": _dec(trade.exit_price),
        "exit_fee": _dec(trade.exit_fee),
        "realized_pnl": _dec(trade.realized_pnl),
        "mfe": _dec(trade.mfe),
        "mae": _dec(trade.mae),
        "outcome": _side(trade.outcome),
        "hold_to_resolution_pnl": _dec(trade.hold_to_resolution_pnl),
    }


def _closed_from_dict(data: dict[str, Any]) -> ClosedTrade:
    return ClosedTrade(
        market_id=data["market_id"],
        group_id=data["group_id"],
        direction=Side(data["direction"]),
        shares=Decimal(data["shares"]),
        avg_entry_price=Decimal(data["avg_entry_price"]),
        cost_basis=Decimal(data["cost_basis"]),
        entry_fee=Decimal(data["entry_fee"]),
        entry_slippage=Decimal(data["entry_slippage"]),
        opened_at=datetime.fromisoformat(data["opened_at"]),
        detection_at=datetime.fromisoformat(data["detection_at"]),
        trader_decision_at=(
            datetime.fromisoformat(data["trader_decision_at"])
            if data["trader_decision_at"]
            else None
        ),
        trader_price=(
            Decimal(data["trader_price"]) if data["trader_price"] is not None else None
        ),
        system_price_at_detection=(
            Decimal(data["system_price_at_detection"])
            if data["system_price_at_detection"] is not None
            else None
        ),
        consensus_score=data["consensus_score"],
        contributors=tuple(data["contributors"]),
        entry_reason=data["entry_reason"],
        strategy_version=data["strategy_version"],
        closed_at=datetime.fromisoformat(data["closed_at"]),
        exit_reason=data["exit_reason"],
        exit_price=(
            Decimal(data["exit_price"]) if data["exit_price"] is not None else None
        ),
        exit_fee=Decimal(data["exit_fee"]),
        realized_pnl=Decimal(data["realized_pnl"]),
        mfe=Decimal(data["mfe"]),
        mae=Decimal(data["mae"]),
        outcome=Side(data["outcome"]) if data["outcome"] else None,
        hold_to_resolution_pnl=(
            Decimal(data["hold_to_resolution_pnl"])
            if data["hold_to_resolution_pnl"] is not None
            else None
        ),
    )


def portfolio_to_dict(portfolio: PaperPortfolio) -> dict[str, Any]:
    return {
        "starting_balance": _dec(portfolio.starting_balance),
        "free_balance": _dec(portfolio.free_balance),
        "strategy_version": portfolio.strategy_version,
        "peak_equity": _dec(portfolio._peak_equity),
        "max_drawdown": _dec(portfolio._max_drawdown),
        "positions": {
            market_id: _position_to_dict(pos)
            for market_id, pos in portfolio.positions.items()
        },
        "closed": [_closed_to_dict(t) for t in portfolio.closed],
    }


def portfolio_from_dict(data: dict[str, Any]) -> PaperPortfolio:
    portfolio = PaperPortfolio(
        starting_balance=Decimal(data["starting_balance"]),
        strategy_version=data["strategy_version"],
    )
    portfolio.free_balance = Decimal(data["free_balance"])
    portfolio._peak_equity = Decimal(data["peak_equity"])
    portfolio._max_drawdown = Decimal(data["max_drawdown"])
    portfolio.positions = {
        market_id: _position_from_dict(pos)
        for market_id, pos in data["positions"].items()
    }
    portfolio.closed = [_closed_from_dict(t) for t in data["closed"]]
    return portfolio
