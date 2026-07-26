"""Does cutting a losing position early help, or just lock in the loss?

The proposal under test: enter around mid odds (~0.70), stay while it goes your
way, and cut when defeat looks likely — recovering part of the stake instead of
losing all of it.

The question that decides it is not "does the exit feel prudent" but:

    conditional on the price having fallen to X, how often does the position
    still win?

If markets are calibrated, a position now priced X wins about X of the time — the
drop is *information already priced in*, and selling at X is a fair trade, not a
rescue. You then pay the spread twice for nothing. If instead the eventual win
rate at price X is materially BELOW X, the drop over-predicts survival and
cutting genuinely saves money.

This module measures that directly, then prices the resulting exit rules.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from decimal import Decimal

from src.backtest.harness import BacktestData, RunConfig, TradeRecord, _record, _signals
from src.domain.models import Side


@dataclass(frozen=True)
class Touch:
    """A position that at some point traded down to `level` (in its own token)."""

    market_id: str
    event_id: str
    direction: Side
    entry_price: Decimal
    level: float
    won: bool


def _dir_price(yes_price: float, direction: Side) -> float:
    return yes_price if direction is Side.YES else (1.0 - yes_price)


def path_after(
    data: BacktestData, market_id: str, direction: Side, after_ts: int
) -> list[tuple[int, float]]:
    """Price path of `direction`'s token after a timestamp."""
    if not data.price_paths:
        return []
    ts_list, yp_list = data.price_paths.get(market_id, ([], []))
    i = bisect.bisect_right(ts_list, after_ts)
    return [
        (ts_list[j], _dir_price(yp_list[j], direction)) for j in range(i, len(ts_list))
    ]


def collect_touches(
    data: BacktestData, cfg: RunConfig, levels: tuple[float, ...]
) -> list[Touch]:
    """For every candidate position, record which price levels it traded down to.

    Direction-agnostic: we take both sides of every market so the sample is not
    conditioned on a strategy that might itself be biased.
    """
    touches: list[Touch] = []
    for market_id, detection_at, meta in _signals(data, cfg):
        for direction in (Side.YES, Side.NO):
            rec = _record(data, market_id, meta, direction, detection_at, cfg)
            if rec is None:
                continue
            won = direction is meta.resolved_outcome
            path = path_after(data, market_id, direction, int(detection_at.timestamp()))
            if not path:
                continue
            low = min(p for _, p in path)
            for level in levels:
                if low <= level < float(rec.entry_price):
                    touches.append(
                        Touch(
                            market_id,
                            meta.event_id,
                            direction,
                            rec.entry_price,
                            level,
                            won,
                        )
                    )
    return touches


def calibration_at_levels(
    touches: list[Touch], levels: tuple[float, ...]
) -> dict[float, tuple[int, float]]:
    """Empirical win rate among positions that traded down to each level.

    Returns level -> (n, observed win rate). Compare the win rate with the level
    itself: roughly equal ⇒ the market is calibrated after the drop ⇒ cutting is
    a fair trade, not a save.
    """
    out: dict[float, tuple[int, float]] = {}
    for level in levels:
        sel = [t for t in touches if t.level == level]
        if not sel:
            out[level] = (0, float("nan"))
            continue
        out[level] = (len(sel), sum(1 for t in sel if t.won) / len(sel))
    return out


def apply_stop_loss(
    data: BacktestData,
    cfg: RunConfig,
    records: list[TradeRecord],
    stop: float,
    *,
    exit_cost: Decimal = Decimal("0.01"),
) -> list[TradeRecord]:
    """Re-price held positions under a stop-loss at `stop` (own-token price).

    `exit_cost` is the round-trip penalty for selling into the book (spread and
    slippage) — cutting is never free, which is the point.
    """
    out: list[TradeRecord] = []
    for r in records:
        path = path_after(
            data, r.market_id, r.direction, int(r.detection_at.timestamp())
        )
        stopped = next((p for _, p in path if p <= stop), None)
        if stopped is None:
            out.append(r)
            continue
        proceeds = Decimal(str(stopped)) - exit_cost
        if proceeds < 0:
            proceeds = Decimal(0)
        out.append(
            TradeRecord(
                market_id=r.market_id,
                event_id=r.event_id,
                category=r.category,
                direction=r.direction,
                entry_price=r.entry_price,
                outcome=r.outcome,
                fee=r.fee,
                pnl_per_share=proceeds - r.entry_price - r.fee,
                detection_at=r.detection_at,
            )
        )
    return out
