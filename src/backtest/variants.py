"""Strategy variants requested for evaluation — including 'follow the top
win-rate traders, majority vote, exit when they exit, fixed dollar stake'.

Every variant is leakage-safe: the top-N list at a signal is built ONLY from
markets resolved before that signal. Ranking by raw win rate is offered because
it was asked for, not because it is sound — the harness exists to test it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.backtest.harness import (
    BacktestData,
    RunConfig,
    TradeRecord,
    _net_direction,
    _record,
    _signals,
    _skills_cache_key,
    as_of_skills,
)
from src.domain.models import Side, TraderTrade
from src.scoring.skill import TraderSkill

_ZERO = Decimal(0)


@dataclass(frozen=True)
class TopNConfig:
    top_n: int = 20
    rank_by: str = "winrate"  # 'winrate' | 'wilson' | 'roi'
    min_sample: int = 5  # ignore 3/3=100% traders
    exit_when_they_exit: bool = True
    exit_fraction: float = 0.5  # majority of followers cutting -> we cut


def _rank_value(s: TraderSkill, how: str) -> float:
    if how == "winrate":
        return s.raw
    if how == "wilson":
        return s.wilson()
    if how == "roi":
        return s.mean_roi
    raise ValueError(how)


def top_traders(
    skills: dict[tuple[str, str], TraderSkill], category: str, cfg: TopNConfig
) -> list[str]:
    """Top-N wallets in a category, as-of, ranked by the chosen metric."""
    pool = [
        (wallet, s)
        for (wallet, cat), s in skills.items()
        if cat == category and s.n >= cfg.min_sample
    ]
    pool.sort(key=lambda ws: (-_rank_value(ws[1], cfg.rank_by), -ws[1].n, ws[0]))
    return [w for w, _ in pool[: cfg.top_n]]


def _followers_in_market(
    data: BacktestData, market_id: str, at: datetime, wallets: list[str]
) -> dict[str, tuple[Side, Decimal]]:
    """Each followed wallet's net direction and size in this market before `at`."""
    by_wallet: dict[str, list[TraderTrade]] = defaultdict(list)
    allowed = set(wallets)
    for t in data.trades:
        if t.market_id == market_id and t.wallet in allowed and t.timestamp < at:
            by_wallet[t.wallet].append(t)
    out: dict[str, tuple[Side, Decimal]] = {}
    for wallet, trades in by_wallet.items():
        direction, size = _net_direction(trades, at)
        if direction is not None:
            out[wallet] = (direction, size)
    return out


def _exit_time(
    data: BacktestData,
    market_id: str,
    followers: dict[str, tuple[Side, Decimal]],
    entered_at: datetime,
    resolved_at: datetime,
    cfg: TopNConfig,
) -> datetime | None:
    """When did a majority of the followed traders cut their position?

    Scans their trades after entry; a wallet 'cut' once its net exposure drops
    below half of what it held at entry (or flips). Returns the timestamp at
    which the cut-share crosses `exit_fraction`, else None (held to resolution).
    """
    if not followers:
        return None
    by_wallet: dict[str, list[TraderTrade]] = defaultdict(list)
    for t in data.trades:
        if (
            t.market_id == market_id
            and t.wallet in followers
            and t.timestamp <= resolved_at
        ):
            by_wallet[t.wallet].append(t)

    events: list[tuple[datetime, str]] = []
    for wallet, (direction, size_at_entry) in followers.items():
        trades = sorted(by_wallet.get(wallet, []), key=lambda t: t.timestamp)
        running = size_at_entry
        for t in trades:
            if t.timestamp <= entered_at:
                continue
            signed = t.yes_delta if direction is Side.YES else -t.yes_delta
            running += signed
            if running <= size_at_entry / 2:
                events.append((t.timestamp, wallet))
                break

    if not events:
        return None
    events.sort()
    needed = max(1, int(len(followers) * cfg.exit_fraction))
    if len(events) < needed:
        return None
    return events[needed - 1][0]


def run_top_winrate_majority(
    data: BacktestData, cfg: RunConfig, top: TopNConfig
) -> tuple[list[TradeRecord], list[TradeRecord]]:
    """Follow the top-N traders' majority direction.

    Returns (records_with_exit_rule, records_hold_to_resolution) over the SAME
    entries, so the exit rule can be judged against simply holding.
    """
    held: list[TradeRecord] = []
    exited: list[TradeRecord] = []
    cache: dict[datetime, dict] = {}

    for market_id, detection_at, meta in _signals(data, cfg):
        key = _skills_cache_key(detection_at)
        if key not in cache:
            cache[key] = as_of_skills(data, key, params=cfg.params)
        skills = cache[key]
        leaders = top_traders(skills, meta.category, top)
        if not leaders:
            continue

        followers = _followers_in_market(data, market_id, detection_at, leaders)
        if len(followers) < cfg.params.min_signal_contributors:
            continue

        yes = sum(1 for d, _ in followers.values() if d is Side.YES)
        no = len(followers) - yes
        if yes == no:
            continue
        direction = Side.YES if yes > no else Side.NO

        rec_hold = _record(data, market_id, meta, direction, detection_at, cfg)
        if rec_hold is None:
            continue
        held.append(rec_hold)

        # Exit rule: leave when a majority of the followed traders cut.
        rec_exit = rec_hold
        if top.exit_when_they_exit:
            agree = {w: v for w, v in followers.items() if v[0] is direction}
            t_exit = _exit_time(
                data, market_id, agree, detection_at, meta.resolved_at, top
            )
            if t_exit is not None:
                sell = data.price_fn(market_id, direction, t_exit)
                if sell is not None:
                    # Sell side of the same token: proceeds ≈ 1 - price(opposite).
                    exit_price = Decimal(1) - sell
                    pnl = exit_price - rec_hold.entry_price - cfg.fee
                    rec_exit = TradeRecord(
                        market_id=rec_hold.market_id,
                        event_id=rec_hold.event_id,
                        category=rec_hold.category,
                        direction=direction,
                        entry_price=rec_hold.entry_price,
                        outcome=meta.resolved_outcome,
                        fee=cfg.fee,
                        pnl_per_share=pnl,
                        detection_at=detection_at,
                    )
        exited.append(rec_exit)

    return exited, held
