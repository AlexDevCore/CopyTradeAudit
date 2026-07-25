"""Run the raw-data -> decisions -> scores pipeline deterministically.

Given a fixed set of raw trades and market outcomes, produce the same trader
scores every time. This is the audit backbone: identical input must yield
identical output regardless of when or where it runs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.domain.models import Side, TraderTrade
from src.domain.params import DEFAULTS, StrategyParams
from src.ingest.polymarket import parse_trade
from src.normalize.decisions import build_decisions
from src.scoring.winrate import TraderScore, score_from_decisions


@dataclass(frozen=True)
class ReplayResult:
    scores: tuple[TraderScore, ...]  # ranked, deterministic order
    total_decisions: int

    def as_rows(self) -> list[dict[str, Any]]:
        """Flat, JSON-friendly view for snapshots/audit."""
        return [
            {
                "wallet": s.wallet,
                "category": s.category,
                "wins": s.wins,
                "losses": s.losses,
                "n": s.n,
                "raw": round(s.raw, 6),
                "wilson": round(s.wilson(), 6),
            }
            for s in self.scores
        ]


def _group_trades(
    raw_trades: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], list[TraderTrade]]:
    grouped: dict[tuple[str, str], list[TraderTrade]] = {}
    for raw in raw_trades:
        trade = parse_trade(raw)
        grouped.setdefault((trade.wallet, trade.market_id), []).append(trade)
    return grouped


def run_replay(
    raw_trades: Sequence[Mapping[str, Any]],
    outcomes: Mapping[str, Side],
    *,
    category_of: Mapping[str, str] | None = None,
    typical_notional_usd: Decimal = Decimal(400),
    params: StrategyParams = DEFAULTS,
) -> ReplayResult:
    """Replay the pipeline.

    ``outcomes`` maps market_id -> resolved Side. ``category_of`` maps
    market_id -> category (defaults to "unknown"); scoring is per (wallet,
    category), never a single global list.
    """
    category_of = category_of or {}
    grouped = _group_trades(raw_trades)

    # wallet -> category -> decisions
    decisions_by_wallet_cat: dict[tuple[str, str], list] = {}
    total_decisions = 0
    for (wallet, market_id), trades in grouped.items():
        decisions = build_decisions(
            trades, typical_notional_usd=typical_notional_usd, params=params
        )
        total_decisions += len(decisions)
        category = category_of.get(market_id, "unknown")
        decisions_by_wallet_cat.setdefault((wallet, category), []).extend(decisions)

    scores: list[TraderScore] = []
    for (wallet, category), decisions in decisions_by_wallet_cat.items():
        scores.append(score_from_decisions(wallet, category, decisions, outcomes))

    # Deterministic ranking: Wilson desc, then n desc, then wallet/category asc.
    scores.sort(key=lambda s: (-s.wilson(), -s.n, s.wallet, s.category))
    return ReplayResult(scores=tuple(scores), total_decisions=total_decisions)
