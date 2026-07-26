"""Leakage-safe copy-strategy backtest.

Design commitments (each defended by a test):

  * No future information. At a signal's detection time `t`, trader skill is
    computed ONLY from markets that RESOLVED strictly before `t`. A market that
    resolves at or after `t` cannot contribute to the pool that trades it.
  * Realized net PnL per share, not win rate. pnl = payoff(0/1) − entry_price −
    fee. A favourite bought at 0.98 that wins scores +0.01, not "a win".
  * Event-clustered uncertainty. Correlated markets share an `event_id`; the
    bootstrap resamples EVENTS, not trades, so we never pretend 50 trades on one
    event are 50 independent observations.

Nothing here proves profitability. It is built to expose the absence of edge.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.domain.models import Side, TraderTrade
from src.domain.params import DEFAULTS, StrategyParams
from src.normalize.decisions import build_decisions
from src.scoring.skill import TraderSkill, skill_from_decisions

_ZERO = Decimal(0)

# our first executable price to BUY `direction` in `market` at/after time `at`
PriceFn = Callable[[str, Side, datetime], "Decimal | None"]


@dataclass(frozen=True)
class MarketMeta:
    market_id: str
    category: str
    event_id: str
    resolved_outcome: Side | None
    resolved_at: datetime | None


@dataclass
class BacktestData:
    trades: list[TraderTrade]
    markets: dict[str, MarketMeta]
    price_fn: PriceFn
    typical_notional: Decimal = Decimal(400)
    market_floors: dict[str, Decimal] | None = None  # per-market decision bar

    def floor_for(self, market_id: str) -> Decimal | None:
        return None if self.market_floors is None else self.market_floors.get(market_id)


def market_size_floors(
    trades: Iterable[TraderTrade], percentile: float
) -> dict[str, Decimal]:
    """Per-market decision bar = that percentile of the market's trade notionals.

    Makes "is this a meaningful bet?" relative to the venue it happens in: $50 in
    a market whose median trade is $6 is a strong signal, the same $50 in a whale
    market is noise.
    """
    by_market: dict[str, list[Decimal]] = defaultdict(list)
    for t in trades:
        by_market[t.market_id].append(abs(t.yes_delta) * t.yes_price)
    floors: dict[str, Decimal] = {}
    for market_id, sizes in by_market.items():
        sizes.sort()
        floors[market_id] = sizes[min(len(sizes) - 1, int(percentile * len(sizes)))]
    return floors


@dataclass(frozen=True)
class TradeRecord:
    market_id: str
    event_id: str
    category: str
    direction: Side
    entry_price: Decimal
    outcome: Side
    fee: Decimal
    pnl_per_share: Decimal  # payoff(1/0) − entry_price − fee
    detection_at: datetime


# --------------------------------------------------------------------------- #
# Leakage-safe pool construction
# --------------------------------------------------------------------------- #


def as_of_skills(
    data: BacktestData, cutoff: datetime, *, params: StrategyParams = DEFAULTS
) -> dict[tuple[str, str], TraderSkill]:
    """Trader skill by (wallet, category) using ONLY markets resolved < cutoff.

    This is the leakage guard: a market resolving at or after `cutoff` is
    invisible to the pool that would trade at `cutoff`.
    """
    by_wm: dict[tuple[str, str], list[TraderTrade]] = defaultdict(list)
    for t in data.trades:
        by_wm[(t.wallet, t.market_id)].append(t)

    dec_by_wc: dict[tuple[str, str], list] = defaultdict(list)
    outcomes: dict[str, Side] = {}
    for (wallet, market_id), trades in by_wm.items():
        meta = data.markets.get(market_id)
        if meta is None or meta.resolved_at is None or meta.resolved_outcome is None:
            continue
        if meta.resolved_at >= cutoff:  # LEAKAGE GUARD
            continue
        usable = [t for t in trades if t.timestamp <= meta.resolved_at]
        decs = build_decisions(
            usable,
            typical_notional_usd=data.typical_notional,
            params=params,
            market_floor_usd=data.floor_for(market_id),
        )
        dec_by_wc[(wallet, meta.category)].extend(decs)
        outcomes[market_id] = meta.resolved_outcome

    return {
        (wallet, category): skill_from_decisions(wallet, category, decs, outcomes)
        for (wallet, category), decs in dec_by_wc.items()
    }


def select_pool(
    skills: dict[tuple[str, str], TraderSkill], params: StrategyParams = DEFAULTS
) -> set[tuple[str, str]]:
    """Eligible (wallet, category) keys: enough resolved markets AND ROI floor.

    Enforces fix (a): the ROI floor removes favourite-buyers whose win rate is
    high but whose price-aware edge is ~0.
    """
    return {
        key
        for key, s in skills.items()
        if s.is_pool_eligible(params.min_resolved_markets, params.min_mean_roi)
    }


def _net_direction(
    trades: Iterable[TraderTrade], cutoff: datetime
) -> tuple[Side | None, Decimal]:
    net = sum((t.yes_delta for t in trades if t.timestamp < cutoff), _ZERO)
    if net > 0:
        return Side.YES, net
    if net < 0:
        return Side.NO, -net
    return None, _ZERO


# --------------------------------------------------------------------------- #
# Strategy + benchmarks (same signal points -> comparable)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RunConfig:
    start: datetime
    end: datetime
    latency_sec: int = 90
    fee: Decimal = _ZERO
    slippage: Decimal = _ZERO  # added to buy price on top of price_fn
    min_weight_vote: float = 0.2  # |skill-weighted net vote| threshold in [0,1]
    params: StrategyParams = DEFAULTS


def _skills_cache_key(dt: datetime) -> datetime:
    # Recompute the as-of pool once per UTC day for speed; still strictly < day.
    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)


def _signals(data: BacktestData, cfg: RunConfig):
    """Yield (market_id, detection_at, meta) for each in-window resolved-market
    trade, one entry per market (first qualifying trade)."""
    seen: set[str] = set()
    for t in sorted(data.trades, key=lambda x: x.timestamp):
        if not (cfg.start <= t.timestamp < cfg.end):
            continue
        meta = data.markets.get(t.market_id)
        if meta is None or meta.resolved_outcome is None:
            continue
        if t.market_id in seen:
            continue
        seen.add(t.market_id)
        yield t.market_id, t.timestamp + timedelta(seconds=cfg.latency_sec), meta


def _weighted_vote(
    data: BacktestData,
    market_id: str,
    detection_at: datetime,
    pool: set[tuple[str, str]],
    skills: dict[tuple[str, str], TraderSkill],
    category: str,
) -> tuple[Side | None, int, float]:
    """Skill-weighted net-direction vote of pooled traders holding in market.

    Returns (direction, n_contributors, strength in [0,1]).
    """
    by_wallet: dict[str, list[TraderTrade]] = defaultdict(list)
    for t in data.trades:
        if t.market_id == market_id and t.timestamp < detection_at:
            by_wallet[t.wallet].append(t)
    signed = 0.0
    total = 0.0
    n = 0
    for wallet, trades in by_wallet.items():
        if (wallet, category) not in pool:
            continue
        direction, _ = _net_direction(trades, detection_at)
        if direction is None:
            continue
        w = max(0.0, skills[(wallet, category)].wilson() - 0.5)
        if w <= 0:
            continue
        signed += w * (1.0 if direction is Side.YES else -1.0)
        total += w
        n += 1
    if total <= 0 or n == 0:
        return None, n, 0.0
    vote = signed / total
    return (Side.YES if vote >= 0 else Side.NO), n, abs(vote)


def _record(
    data: BacktestData, market_id, meta, direction, detection_at, cfg
) -> TradeRecord | None:
    price = data.price_fn(market_id, direction, detection_at)
    if price is None:
        return None
    entry = price + cfg.slippage
    if entry <= 0 or entry >= 1:
        return None
    payoff = Decimal(1) if direction is meta.resolved_outcome else _ZERO
    pnl = payoff - entry - cfg.fee
    return TradeRecord(
        market_id=market_id,
        event_id=meta.event_id,
        category=meta.category,
        direction=direction,
        entry_price=entry,
        outcome=meta.resolved_outcome,
        fee=cfg.fee,
        pnl_per_share=pnl,
        detection_at=detection_at,
    )


def run_copy_strategy(data: BacktestData, cfg: RunConfig) -> list[TradeRecord]:
    """The leakage-safe copy strategy: skill-weighted net direction, hold to res."""
    records: list[TradeRecord] = []
    cache: dict[datetime, tuple[dict, set]] = {}
    for market_id, detection_at, meta in _signals(data, cfg):
        key = _skills_cache_key(detection_at)
        if key not in cache:
            skills = as_of_skills(data, key, params=cfg.params)
            cache[key] = (skills, select_pool(skills, cfg.params))
        skills, pool = cache[key]
        direction, n, strength = _weighted_vote(
            data, market_id, detection_at, pool, skills, meta.category
        )
        if direction is None or n < cfg.params.min_signal_contributors:
            continue
        if strength < cfg.min_weight_vote:
            continue
        rec = _record(data, market_id, meta, direction, detection_at, cfg)
        if rec is not None:
            records.append(rec)
    return records


def run_benchmark(
    data: BacktestData, cfg: RunConfig, kind: str, *, seed: int = 0
) -> list[TradeRecord]:
    """Benchmarks entered at the SAME markets/prices as the strategy is offered.

    kinds: 'random', 'always_yes', 'majority', 'market_favorite'.
    'no_trade' returns []. 'hold_to_resolution' is the strategy's own exit, so
    it is not a separate direction rule here.
    """
    rng = random.Random(seed)
    records: list[TradeRecord] = []
    for market_id, detection_at, meta in _signals(data, cfg):
        if kind == "random":
            direction = Side.YES if rng.random() < 0.5 else Side.NO
        elif kind == "always_yes":
            direction = Side.YES
        elif kind == "majority":
            by_wallet: dict[str, list[TraderTrade]] = defaultdict(list)
            for t in data.trades:
                if t.market_id == market_id and t.timestamp < detection_at:
                    by_wallet[t.wallet].append(t)
            yes = sum(
                1
                for tr in by_wallet.values()
                if _net_direction(tr, detection_at)[0] is Side.YES
            )
            no = sum(
                1
                for tr in by_wallet.values()
                if _net_direction(tr, detection_at)[0] is Side.NO
            )
            if yes == no:
                continue
            direction = Side.YES if yes > no else Side.NO
        elif kind == "market_favorite":
            # Buy the market's favourite: the side priced ABOVE 0.5.
            py = data.price_fn(market_id, Side.YES, detection_at)
            if py is None:
                continue
            direction = Side.YES if py > Decimal("0.5") else Side.NO
        else:
            raise ValueError(f"unknown benchmark {kind!r}")
        rec = _record(data, market_id, meta, direction, detection_at, cfg)
        if rec is not None:
            records.append(rec)
    return records
