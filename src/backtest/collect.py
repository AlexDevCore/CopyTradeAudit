"""Collect REAL resolved-market data from public read-only Polymarket APIs.

Network-only (never imported by tests). Writes a JSON cache so the backtest is a
deterministic replay from stored data — the same cache always yields the same
result. No keys, no trading, read-only.

Executable-price proxy: we do NOT have historical L2 depth, so the price our
strategy would face at detection is approximated by the market's own most-recent
trade price at/before that instant, plus a conservative fixed slippage. This is
a documented limitation (no depth, no partial-fill modelling).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"

_CLIENT = httpx.Client(timeout=30.0)


def _get(url: str, **params: Any) -> Any:
    for attempt in range(5):
        r = _CLIENT.get(url, params=params)
        if r.status_code == 429:
            time.sleep(1.0 + attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def _epoch(iso: str | None) -> int | None:
    if not iso:
        return None
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _tag_id(slug: str) -> str:
    # /tags?limit=N is capped at 100, so resolve by slug directly.
    t = _get(f"{GAMMA}/tags/slug/{slug}")
    return str(t["id"])


def _resolved_outcome(market: dict) -> str | None:
    prices = market.get("outcomePrices")
    if isinstance(prices, str):
        prices = json.loads(prices)
    if not prices or len(prices) != 2:
        return None
    y, n = float(prices[0]), float(prices[1])
    if y >= 0.99 and n <= 0.01:
        return "YES"
    if n >= 0.99 and y <= 0.01:
        return "NO"
    return None  # undecided / not cleanly binary


def _collect_markets(
    tag_id: str, *, days: int, max_markets: int, min_volume: float
) -> list[dict]:
    cutoff = time.time() - days * 86400
    out: list[dict] = []
    pages = 0
    while len(out) < max_markets and pages < 25:
        params = dict(
            closed="true",
            tag_id=tag_id,
            limit=100,
            order="endDate",
            ascending="false",
            offset=pages * 100,
        )
        try:
            batch = _get(f"{GAMMA}/markets", **params)
        except httpx.HTTPStatusError:
            break  # offset exhausted (Gamma caps deep pagination)
        pages += 1
        if not batch:
            break
        for m in batch:
            end = _epoch(m.get("endDate"))
            if end is None or end < cutoff:
                continue
            if not m.get("enableOrderBook") or (m.get("volumeNum") or 0) < min_volume:
                continue
            outcome = _resolved_outcome(m)
            if outcome is None:
                continue
            toks = m.get("clobTokenIds")
            if isinstance(toks, str):
                toks = json.loads(toks)
            if not toks:
                continue
            ev = (m.get("events") or [{}])[0]
            # Real resolution time: prefer market/event closedTime; endDate is only
            # the scheduled date (00:00), often BEFORE same-day trading resolves.
            resolved_at = (
                _epoch(m.get("closedTime"))
                or _epoch(ev.get("closedTime"))
                or (end + 86400)
            )
            out.append(
                {
                    "market_id": m["conditionId"],
                    "yes_token": toks[0],
                    "question": m.get("question"),
                    "event_id": str(ev.get("id") or m["conditionId"]),
                    "category": "sports",
                    "resolved_outcome": outcome,
                    "resolved_at": resolved_at,
                    "volume": m.get("volumeNum"),
                    "liquidity": m.get("liquidityNum"),
                }
            )
            if len(out) >= max_markets:
                break
        # endDate-desc: once a whole page is older than cutoff, stop
        if all((_epoch(m.get("endDate")) or 0) < cutoff for m in batch):
            break
        time.sleep(0.05)
    return out


def _collect_trades(
    market_id: str, *, cap: int = 1500, max_pages: int = 6
) -> list[dict]:
    """Fetch up to `cap` most-recent trades for a market (paginate by `before`).

    We do NOT drop post-resolution trades here — every fetched row counts toward
    `cap`, so a market with many trades stops after a few pages instead of paging
    forever. Resolution-time filtering happens downstream in the harness.
    """
    trades: list[dict] = []
    before = None
    seen: set[str] = set()
    pages = 0
    while len(trades) < cap and pages < max_pages:
        params = dict(market=market_id, limit=500)
        if before:
            params["before"] = before
        batch = _get(f"{DATA}/trades", **params)
        pages += 1
        if not batch:
            break
        oldest = None
        for x in batch:
            ts = int(x.get("timestamp", 0))
            oldest = ts if oldest is None else min(oldest, ts)
            key = f"{x.get('transactionHash')}:{x.get('proxyWallet')}:{x.get('outcome')}:{ts}"
            if key in seen:
                continue
            seen.add(key)
            trades.append(
                {
                    "wallet": x.get("proxyWallet"),
                    "side": x.get("side"),
                    "outcome": x.get("outcome"),
                    "price": x.get("price"),
                    "size": x.get("size"),
                    "timestamp": ts,
                }
            )
        if len(batch) < 500 or oldest is None:
            break
        before = str(oldest)
        time.sleep(0.03)
    return trades


def collect(
    *,
    days: int = 90,
    max_markets: int = 120,
    min_volume: float = 5000.0,
    out_path: str = "data/real_sports_90d.json",
) -> str:
    tag = _tag_id("sports")
    markets = _collect_markets(
        tag, days=days, max_markets=max_markets, min_volume=min_volume
    )
    print(f"markets selected: {len(markets)} — fetching trades…", flush=True)
    total_trades = 0
    for i, m in enumerate(markets, 1):
        m["trades"] = _collect_trades(m["market_id"], cap=1500)
        total_trades += len(m["trades"])
        if i % 20 == 0 or i == len(markets):
            print(f"  {i}/{len(markets)} markets, {total_trades} trades", flush=True)
    payload = {
        "meta": {
            "collected_at": datetime.now(tz=timezone.utc).isoformat(),
            "days": days,
            "category": "sports",
            "n_markets": len(markets),
            "n_trades": total_trades,
            "source": "public read-only Gamma+Data API",
            "price_proxy": "last trade price at/before detection + fixed slippage (no L2 depth)",
        },
        "markets": markets,
    }
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    p = collect()
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    meta = data["meta"]
    wallets = {t["wallet"] for m in data["markets"] for t in m["trades"]}
    print(f"cache -> {p}")
    print(
        f"markets={meta['n_markets']} trades={meta['n_trades']} unique_wallets={len(wallets)}"
    )
