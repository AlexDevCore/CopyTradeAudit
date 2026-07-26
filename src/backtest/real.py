"""Load the cached real sports data and run the leakage-safe harness on it.

Deterministic replay from the on-disk cache produced by `collect.py`. The
executable price is proxied from the market's own trade price series (last trade
at/before detection) + fixed slippage — no L2 depth (documented limitation).

Usage: python -m src.backtest.real
"""

from __future__ import annotations

import bisect
import gzip
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from src.backtest.harness import (
    BacktestData,
    MarketMeta,
    RunConfig,
    market_size_floors,
    run_benchmark,
    run_copy_strategy,
)
from src.backtest.metrics import Metrics, summarize
from src.domain.models import Action, Side, TraderTrade
from src.domain.params import DEFAULTS, StrategyParams

CACHE = "data/real_sports_90d.json.gz"


def _yes_price(outcome: str, price: float) -> float:
    return price if str(outcome).lower().startswith("y") else (1.0 - price)


def read_cache(path: str = CACHE) -> dict:
    """Read the committed dataset log (.gz or plain .json)."""
    p = Path(path)
    if not p.exists() and p.suffix == ".gz":
        p = p.with_suffix("")  # fall back to uncompressed
    if p.suffix == ".gz":
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(p.read_text(encoding="utf-8"))


def load(
    path: str = CACHE, *, percentile: float | None = None
) -> tuple[BacktestData, dict]:
    payload = read_cache(path)
    markets: dict[str, MarketMeta] = {}
    trades: list[TraderTrade] = []
    series: dict[str, tuple[list[int], list[float]]] = {}

    for m in payload["markets"]:
        mid = m["market_id"]
        markets[mid] = MarketMeta(
            market_id=mid,
            category=m["category"],
            event_id=m["event_id"],
            resolved_outcome=Side(m["resolved_outcome"]),
            resolved_at=datetime.fromtimestamp(m["resolved_at"], tz=timezone.utc),
        )
        rows = sorted(m["trades"], key=lambda x: x["timestamp"])
        ts_list: list[int] = []
        yp_list: list[float] = []
        for t in rows:
            if t["wallet"] is None or t["price"] is None or t["size"] is None:
                continue
            side = Side.YES if str(t["outcome"]).lower().startswith("y") else Side.NO
            action = Action.BUY if str(t["side"]).upper() == "BUY" else Action.SELL
            trades.append(
                TraderTrade.from_token_trade(
                    wallet=t["wallet"],
                    market_id=mid,
                    side=side,
                    action=action,
                    shares=Decimal(str(t["size"])),
                    price=Decimal(str(t["price"])),
                    timestamp=datetime.fromtimestamp(
                        int(t["timestamp"]), tz=timezone.utc
                    ),
                )
            )
            ts_list.append(int(t["timestamp"]))
            yp_list.append(_yes_price(t["outcome"], float(t["price"])))
        series[mid] = (ts_list, yp_list)

    slippage = 0.01

    def price_fn(market_id: str, direction: Side, at: datetime) -> Decimal | None:
        ts_list, yp_list = series.get(market_id, ([], []))
        if not ts_list:
            return None
        i = bisect.bisect_right(ts_list, int(at.timestamp())) - 1
        yp = yp_list[i] if i >= 0 else yp_list[0]
        buy = yp if direction is Side.YES else (1.0 - yp)
        buy = min(0.98, max(0.02, buy + slippage))
        return Decimal(str(round(buy, 4)))

    pct = DEFAULTS.market_size_percentile if percentile is None else percentile
    floors = market_size_floors(trades, pct)
    data = BacktestData(
        trades=trades, markets=markets, price_fn=price_fn, market_floors=floors
    )
    return data, payload["meta"]


def _split_time(data: BacktestData) -> tuple[datetime, datetime]:
    res = sorted(m.resolved_at for m in data.markets.values())
    mid = res[len(res) // 2]
    end = res[-1] + timedelta(days=1)
    return mid, end


def paper_pnl(records, *, balance: Decimal, stake: Decimal) -> tuple[Decimal, Decimal]:
    """Dollar paper P&L for a fixed stake per trade -> (pnl, total staked)."""
    total = Decimal(0)
    staked = Decimal(0)
    for r in records:
        shares = stake / r.entry_price
        total += shares * r.pnl_per_share
        staked += stake
    return total, staked


def run(
    path: str = CACHE,
    *,
    stake: Decimal = Decimal(5),
    balance: Decimal = Decimal(1000),
    min_resolved_options: tuple[int, ...] = (30, 10, 5),
    percentile: float | None = None,
) -> dict:
    data, meta = load(path, percentile=percentile)
    wallets = {t.wallet for t in data.trades}
    start, end = _split_time(data)

    def cfg(min_resolved: int) -> RunConfig:
        return RunConfig(
            start=start,
            end=end,
            latency_sec=90,
            fee=Decimal(0),
            slippage=Decimal(0),  # slippage already baked into price_fn
            params=StrategyParams(min_resolved_markets=min_resolved),
        )

    results: dict[str, dict[str, tuple[Metrics, Decimal, Decimal]]] = {}
    for mr in min_resolved_options:
        c = cfg(mr)
        row: dict[str, tuple[Metrics, Decimal, Decimal]] = {}
        recs = run_copy_strategy(data, c)
        row["copy_strategy"] = (
            summarize(recs),
            *paper_pnl(recs, balance=balance, stake=stake),
        )
        for kind in ("majority", "market_favorite", "random"):
            b = run_benchmark(data, c, kind)
            row[kind] = (summarize(b), *paper_pnl(b, balance=balance, stake=stake))
        results[f"min_resolved={mr}"] = row

    floors = sorted(data.market_floors.values()) if data.market_floors else []
    return {
        "meta": meta,
        "n_wallets": len(wallets),
        "split": (start, end),
        "results": results,
        "stake": stake,
        "balance": balance,
        "median_market_floor": floors[len(floors) // 2] if floors else None,
    }


def _fmt(m: Metrics, pnl: Decimal, staked: Decimal, balance: Decimal) -> str:
    verdict = "EDGE" if m.ci_excludes_zero and m.mean_pnl_per_share > 0 else "no-edge"
    roi = (pnl / staked * 100) if staked else Decimal(0)
    return (
        f"n={m.n_trades:4d} ev={m.n_events:3d} PnL=${float(pnl):+8.2f} "
        f"ROI={float(roi):+6.1f}% end=${float(balance + pnl):8.2f} "
        f"CI/sh[{m.ci_low:+.3f},{m.ci_high:+.3f}] {verdict:7s} wr={m.win_rate:.2f} "
        f"top5={m.top5_share:.2f}"
    )


def main() -> None:
    r = run()
    meta = r["meta"]
    print(
        f"REAL sports cache: markets={meta['n_markets']} trades={meta['n_trades']} "
        f"wallets={r['n_wallets']} collected={meta['collected_at']}"
    )
    print(f"price proxy: {meta['price_proxy']}")
    print(
        f"decision bar: market-relative p{DEFAULTS.market_size_percentile:.0%} "
        f"(median floor ${float(r['median_market_floor'] or 0):.2f}), "
        f"dust guard ${float(DEFAULTS.min_notional_usd):.0f}"
    )
    s, e = r["split"]
    print(f"stake ${float(r['stake']):.2f}/trade on ${float(r['balance']):.0f} balance")
    print(
        f"walk-forward: {s.date()} .. {e.date()} (pool uses only earlier-resolved markets)\n"
    )
    for setting, row in r["results"].items():
        print(f"=== {setting} ===")
        for name, (m, pnl, staked) in row.items():
            print(f"  {name:16s} {_fmt(m, pnl, staked, r['balance'])}")


if __name__ == "__main__":
    main()
