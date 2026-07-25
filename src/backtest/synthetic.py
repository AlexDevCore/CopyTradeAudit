"""Controlled synthetic worlds for validating the harness (NOT profit proof).

Ground truth is known, so we can check three things the harness must get right:
  1. Recover edge when it exists (price inefficiency + skilled traders).
  2. Report ~zero when the market is efficient (price == fair probability).
  3. Never let future information inflate the pool.

`efficiency` in [0,1] is how much the executable price reflects fair value:
  price(YES) = 0.5 + efficiency * (p_yes - 0.5).
At efficiency=1 the price is fair and every direction has EV 0. Below 1 the
favourite side is underpriced, so an edge exists — but note the `market_favorite`
benchmark can capture it WITHOUT any trader copying.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.backtest.harness import BacktestData, MarketMeta
from src.domain.models import Action, Side, TraderTrade

DT0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _buy_price(p_yes: float, direction: Side, efficiency: float) -> Decimal:
    yes = 0.5 + efficiency * (p_yes - 0.5)
    price = yes if direction is Side.YES else (1.0 - yes)
    price = min(0.98, max(0.02, price))
    return Decimal(str(round(price, 4)))


def _trade(wallet, market_id, direction, token_price, ts) -> TraderTrade:
    return TraderTrade.from_token_trade(
        wallet=wallet,
        market_id=market_id,
        side=direction,
        action=Action.BUY,
        shares=Decimal(500),  # ~$250 notional > the $100 decision threshold
        price=token_price,
        timestamp=ts,
    )


def make_world(
    *,
    seed: int = 0,
    n_events: int = 220,
    efficiency: float = 0.3,
    skill_prob: float = 0.85,
    n_skilled: int = 8,
    n_noise: int = 8,
    n_fav: int = 4,
    participation: float = 0.7,
) -> BacktestData:
    rng = random.Random(seed)
    trades: list[TraderTrade] = []
    markets: dict[str, MarketMeta] = {}
    p_map: dict[str, float] = {}

    for e in range(n_events):
        resolved_at = DT0 + timedelta(days=e, hours=12)
        n_mk = 1 if rng.random() < 0.5 else 2
        fav_is_yes = rng.random() < 0.5
        p_yes = 0.75 if fav_is_yes else 0.25
        fav = Side.YES if fav_is_yes else Side.NO
        for k in range(n_mk):
            mid = f"m{e}_{k}"
            outcome = Side.YES if rng.random() < p_yes else Side.NO
            markets[mid] = MarketMeta(mid, "synthetic", f"e{e}", outcome, resolved_at)
            p_map[mid] = p_yes
            ts = resolved_at - timedelta(hours=2)

            for i in range(n_skilled):
                if rng.random() > participation:
                    continue
                d = fav if rng.random() < skill_prob else _flip(fav)
                trades.append(
                    _trade(f"skill{i}", mid, d, _buy_price(p_yes, d, efficiency), ts)
                )
            for i in range(n_noise):
                if rng.random() > participation:
                    continue
                d = Side.YES if rng.random() < 0.5 else Side.NO
                trades.append(
                    _trade(f"noise{i}", mid, d, _buy_price(p_yes, d, efficiency), ts)
                )
            for i in range(n_fav):
                if rng.random() > participation:
                    continue
                # favourite-buyer: always the favourite, but bought expensive (0.95)
                trades.append(_trade(f"fav{i}", mid, fav, Decimal("0.95"), ts))

    def price_fn(market_id: str, direction: Side, at: datetime) -> Decimal:
        return _buy_price(p_map[market_id], direction, efficiency)

    return BacktestData(trades=trades, markets=markets, price_fn=price_fn)


def _flip(side: Side) -> Side:
    return Side.NO if side is Side.YES else Side.YES
