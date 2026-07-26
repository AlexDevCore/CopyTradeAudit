"""Metrics over TradeRecords, with event-clustered uncertainty.

The headline number is mean net PnL per share with a bootstrap confidence
interval that resamples EVENTS, not trades — because markets in one event are
correlated and treating each trade as independent fabricates significance.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from src.backtest.harness import TradeRecord

_ZERO = Decimal(0)


@dataclass(frozen=True)
class Metrics:
    n_trades: int
    n_events: int
    net_pnl: float
    mean_pnl_per_share: float
    win_rate: float
    ci_low: float
    ci_high: float
    profit_factor: float
    top5_share: float  # fraction of gross positive PnL from the 5 biggest wins
    mean_entry_price: float = 0.0

    @property
    def no_observed_losses(self) -> bool:
        return self.n_trades > 0 and self.win_rate >= 1.0

    @property
    def tail_blind(self) -> bool:
        """True when the bootstrap physically cannot see the downside.

        An empirical bootstrap resamples only outcomes that occurred. If a
        near-certainty book won every single trade, the sample contains no loss,
        so the interval is tight and positive while the real distribution still
        carries a rare −(entry) per share. Treating that as significance is how
        a 98¢ book looks like a sure thing right up until it isn't.
        """
        return self.no_observed_losses and self.mean_entry_price >= 0.90

    @property
    def ci_excludes_zero(self) -> bool:
        if self.tail_blind:
            return False  # refuse to certify an edge the sample cannot test
        return self.ci_low > 0.0 or self.ci_high < 0.0


def _event_means(records: list[TradeRecord]) -> dict[str, float]:
    by_event: dict[str, list[float]] = defaultdict(list)
    for r in records:
        by_event[r.event_id].append(float(r.pnl_per_share))
    return {ev: sum(v) / len(v) for ev, v in by_event.items()}


MIN_EVENTS_FOR_CI = 8
"""Below this many independent events we refuse to publish an interval.

A bootstrap over 2-3 events is degenerate: it can return a zero-width interval
(e.g. [+0.020,+0.020]) that looks like overwhelming significance when it is
actually no evidence at all. Refusing is the honest answer.
"""


def event_clustered_ci(
    records: list[TradeRecord], *, iters: int = 2000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float]:
    """Percentile bootstrap CI for mean PnL/share, resampling events.

    Each event contributes its own mean; we resample the set of events with
    replacement. Fewer independent events -> a wider, honest interval, and below
    ``MIN_EVENTS_FOR_CI`` we return an infinite interval rather than a fake one.
    """
    means = list(_event_means(records).values())
    if len(means) < MIN_EVENTS_FOR_CI:
        return (float("-inf"), float("inf"))
    rng = random.Random(seed)
    n = len(means)
    boots: list[float] = []
    for _ in range(iters):
        sample = [means[rng.randrange(n)] for _ in range(n)]
        boots.append(sum(sample) / n)
    boots.sort()
    lo = boots[int((alpha / 2) * iters)]
    hi = boots[int((1 - alpha / 2) * iters)]
    return lo, hi


def summarize(records: list[TradeRecord], *, seed: int = 0) -> Metrics:
    if not records:
        return Metrics(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    pnls = [float(r.pnl_per_share) for r in records]
    net = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    top5 = sum(sorted(wins, reverse=True)[:5])
    top5_share = (top5 / gross_win) if gross_win > 0 else 0.0
    lo, hi = event_clustered_ci(records, seed=seed)
    n_events = len({r.event_id for r in records})
    return Metrics(
        n_trades=len(records),
        n_events=n_events,
        net_pnl=net,
        mean_pnl_per_share=net / len(records),
        win_rate=len(wins) / len(records),
        ci_low=lo,
        ci_high=hi,
        profit_factor=profit_factor,
        top5_share=top5_share,
        mean_entry_price=sum(float(r.entry_price) for r in records) / len(records),
    )
