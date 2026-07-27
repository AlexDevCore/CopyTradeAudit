"""Run the weather-forecast edge test end to end.

    uv run python -m src.backtest.run_weather

Asks: did a free day-ahead public forecast price Polymarket's daily temperature
ladders better than the market? Leakage controls: day-1 forecast runs only, market
price taken at the same cutoff, and the forecast-error sigma for each event is
estimated leaving that event out.
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from src.backtest.harness import TradeRecord
from src.backtest.metrics import summarize
from src.backtest.weather import (
    bucket_probability,
    collect_events,
    estimate_sigma,
    market_price_before,
)
from src.domain.models import Side

CACHE = "data/weather_events.json"
COST = 0.01  # per-share round-trip cost assumption (spread/slippage)


def build(refresh: bool = False) -> list[dict]:
    path = Path(CACHE)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    events = collect_events()
    print(f"closed temperature events with parsed buckets: {len(events)}")
    sigma, n = estimate_sigma(events)  # also fills forecast/actual per event
    print(f"forecast-error sigma (pooled): {sigma:.2f} °C from {n} events")
    # Cutoff = 06:00 local time on the event day. These ladders only open ~12h
    # before resolution, so an "end − 24h" cutoff predates all trading and silently
    # drops every liquid bucket. A late-in-day cutoff would be worse: the market
    # would already see the actual max (reached ~14–16h local) while our day-ahead
    # forecast could not. 06:00 local is the point where the forecast exists and
    # the outcome does not.
    for i, ev in enumerate(events, 1):
        cutoff = int(
            datetime.fromisoformat(f"{ev['day']}T06:00:00")
            .replace(tzinfo=ZoneInfo(ev["tz"]))
            .timestamp()
        )
        for b in ev["buckets"]:
            b["price"] = market_price_before(b["market_id"], cutoff)
            time.sleep(0.03)
        if i % 10 == 0 or i == len(events):
            print(f"  priced {i}/{len(events)} events", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events), encoding="utf-8")
    return events


def loo_sigma(events: list[dict], skip_event_id: str) -> float:
    """Leave-one-out forecast-error sigma: never use the event being priced."""
    errs = [
        ev["actual"] - ev["forecast"]
        for ev in events
        if ev["event_id"] != skip_event_id
        and ev.get("forecast") is not None
        and ev.get("actual") is not None
    ]
    return (statistics.pstdev(errs) or 1.0) if len(errs) >= 3 else 1.5


def run(
    events: list[dict], *, min_edge: float, max_price: float = 0.95
) -> list[TradeRecord]:
    recs: list[TradeRecord] = []
    for ev in events:
        if ev.get("forecast") is None:
            continue
        sigma = loo_sigma(events, ev["event_id"])
        for b in ev["buckets"]:
            price = b.get("price")
            if price is None or not (0.01 < price < max_price):
                continue
            p_model = bucket_probability(b["kind"], b["value"], ev["forecast"], sigma)
            edge = p_model - price - COST
            if edge < min_edge:
                continue
            payoff = Decimal(1) if b["won"] else Decimal(0)
            entry = Decimal(str(round(price + COST, 4)))
            recs.append(
                TradeRecord(
                    market_id=b["market_id"] or f"{ev['event_id']}-{b['value']}",
                    event_id=ev["event_id"],
                    category="weather",
                    direction=Side.YES,
                    entry_price=entry,
                    outcome=Side.YES if b["won"] else Side.NO,
                    fee=Decimal(0),
                    pnl_per_share=payoff - entry,
                    detection_at=datetime.now(tz=timezone.utc),
                )
            )
    return recs


def main() -> None:
    events = build()
    usable = [
        e
        for e in events
        if e.get("forecast") is not None and e.get("actual") is not None
    ]
    priced = sum(1 for e in events for b in e["buckets"] if b.get("price") is not None)
    print(
        f"\nevents: {len(events)} | with forecast+actual: {len(usable)} | priced buckets: {priced}"
    )
    if usable:
        errs = [e["actual"] - e["forecast"] for e in usable]
        print(
            f"day-1 forecast error: mean={statistics.mean(errs):+.2f}°C "
            f"sd={statistics.pstdev(errs):.2f}°C  (this is the model's real accuracy)"
        )

    print(
        f"\n{'min_edge':>9} {'n':>4} {'ev':>4} {'mean/sh':>9} {'CI':>22} {'wr':>5} {'verdict'}"
    )
    for min_edge in (0.02, 0.05, 0.10, 0.20):
        recs = run(events, min_edge=min_edge)
        m = summarize(recs)
        ci = f"[{m.ci_low:+.3f},{m.ci_high:+.3f}]" if m.n_events >= 8 else "[<8 events]"
        if m.tail_blind:
            v = "TAIL-BLIND"
        elif m.ci_excludes_zero and m.mean_pnl_per_share > 0:
            v = "EDGE"
        elif m.ci_excludes_zero:
            v = "LOSS"
        else:
            v = "no-edge"
        print(
            f"{min_edge:>9.2f} {m.n_trades:>4} {m.n_events:>4} "
            f"{m.mean_pnl_per_share:>+9.4f} {ci:>22} {m.win_rate:>5.2f} {v}"
        )


if __name__ == "__main__":
    main()
