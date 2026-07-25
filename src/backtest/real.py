"""Load the cached real sports data and run the leakage-safe harness on it.

Deterministic replay from the on-disk cache produced by `collect.py`. The
executable price is proxied from the market's own trade price series (last trade
at/before detection) + fixed slippage — no L2 depth (documented limitation).

Usage: python -m src.backtest.real
"""

from __future__ import annotations

import bisect
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from src.backtest.harness import (
    BacktestData,
    MarketMeta,
    RunConfig,
    run_benchmark,
    run_copy_strategy,
)
from src.backtest.metrics import Metrics, summarize
from src.domain.models import Action, Side, TraderTrade
from src.domain.params import StrategyParams

CACHE = "data/real_sports_90d.json"


def _yes_price(outcome: str, price: float) -> float:
    return price if str(outcome).lower().startswith("y") else (1.0 - price)


def load(path: str = CACHE) -> tuple[BacktestData, dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
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

    return BacktestData(trades=trades, markets=markets, price_fn=price_fn), payload[
        "meta"
    ]


def _split_time(data: BacktestData) -> tuple[datetime, datetime]:
    res = sorted(m.resolved_at for m in data.markets.values())
    mid = res[len(res) // 2]
    end = res[-1] + timedelta(days=1)
    return mid, end


def run(path: str = CACHE) -> dict:
    data, meta = load(path)
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

    results: dict[str, dict[str, Metrics]] = {}
    for mr in (30, 10, 5):
        c = cfg(mr)
        row: dict[str, Metrics] = {
            "copy_strategy": summarize(run_copy_strategy(data, c))
        }
        for kind in ("majority", "market_favorite", "random"):
            row[kind] = summarize(run_benchmark(data, c, kind))
        results[f"min_resolved={mr}"] = row

    return {
        "meta": meta,
        "n_wallets": len(wallets),
        "split": (start, end),
        "results": results,
    }


def _fmt(m: Metrics) -> str:
    verdict = "EDGE" if m.ci_excludes_zero and m.mean_pnl_per_share > 0 else "no-edge"
    return (
        f"n={m.n_trades:4d} ev={m.n_events:3d} mean={m.mean_pnl_per_share:+.4f} "
        f"CI[{m.ci_low:+.4f},{m.ci_high:+.4f}] {verdict:7s} wr={m.win_rate:.2f} "
        f"pf={m.profit_factor:.2f} top5={m.top5_share:.2f}"
    )


def main() -> None:
    r = run()
    meta = r["meta"]
    print(
        f"REAL sports cache: markets={meta['n_markets']} trades={meta['n_trades']} "
        f"wallets={r['n_wallets']} collected={meta['collected_at']}"
    )
    print(f"price proxy: {meta['price_proxy']}")
    s, e = r["split"]
    print(
        f"walk-forward test window: {s.date()} .. {e.date()} (pool uses only earlier-resolved markets)\n"
    )
    for setting, row in r["results"].items():
        print(f"=== {setting} ===")
        for name, m in row.items():
            print(f"  {name:16s} {_fmt(m)}")


if __name__ == "__main__":
    main()
