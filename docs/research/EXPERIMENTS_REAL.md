# EXPERIMENTS_REAL — first real-data pilot (Sports, 90d)

**This is a real backtest on public Polymarket data, not synthetic.** It was built
to try to DISPROVE a copy edge, and it does not find one. Read the limitations.

## Data

- Source: public read-only Gamma + Data API (keyless). Collector: `src/backtest/collect.py`.
  Deterministic replay from the on-disk cache (`data/…json`, git-ignored).
- Category **Sports**, resolved markets, ~90 days. Collected 2026-07-25.
- **120 markets · 24,376 trades · 5,780 unique wallets.**
- Executable-price proxy: last trade price at/before detection + fixed slippage
  (**no L2 depth**, no partial-fill modelling). Fees `base_fee = 0` (live).
- Walk-forward: pool at each signal uses only markets **resolved before** that
  signal (as-of); test window ≈ 2026-05-22 … 2026-07-14.

## Headline result

With the **conservative, leakage-safe design defaults, the copy strategy makes
ZERO trades** — it cannot even form a pool. Reasons, measured on the cache:

| Structural fact | Value |
|---|---|
| Trades below the $100 decision threshold ("dust") | **23,203 / 24,376 = 95%** |
| Max resolved *decisions* by any single trader (90d) | **28** |
| Traders reaching the default floor (≥30 resolved) | **0** |
| Traders with ≥10 / ≥5 / ≥3 resolved decisions | 25 / 51 / 98 |
| Pool size @min_resolved 30 / 10 / 5 / 3 (ROI floor 0.02) | **0** / 6 / 14 / 26 |

Sports flow is dominated by one-off retail micro-bets; the handful of repeat
traders rarely co-occur in the same market, so a ≥2-independent-expert consensus
almost never forms.

## Strategy vs benchmarks (walk-forward, event-clustered 95% CI)

| strategy | n | events | mean PnL/sh | 95% CI | verdict | win rate | top5 share |
|---|---|---|---|---|---|---|---|
| **copy_strategy** (defaults, min_resolved 30/10/5) | **0** | 0 | — | — | **inert** | — | — |
| majority | 47 | 10 | −0.0094 | [−0.076, +0.059] | no-edge | 0.89 | 0.45 |
| market_favorite | 49 | 10 | +0.0144 | [+0.016, +0.123] | "EDGE"* | 0.96 | 0.47 |
| random | 49 | 10 | +0.0291 | [−0.053, +0.085] | no-edge | 0.55 | 0.78 |

\* Not credible: **10 events only**, 47% of gross profit from the top-5 trades,
win rate 0.96 = buying heavy favourites (favourite-longshot artifact). `random`
even posted a higher mean here — the sample is too thin to conclude anything.

### Forced exploratory run (reckless, overfit-prone — for information only)

Relaxing to `min_resolved=3, min_contributors=1, min_vote=0`:

| | n | events | mean | 95% CI | verdict |
|---|---|---|---|---|---|
| copy_strategy (forced) | 24 | **5** | +0.0170 | **[−0.112, +0.028]** | **no-edge** |
| copy (min_resolved 5, contributors 2) | 0 | 0 | — | — | inert |

Even when forced to fire, the CI **includes zero and skews negative** on just 5
events. No edge survives.

## Interpretation

1. On real 90-day Sports data, the strategy as designed is **structurally inert**
   — not "unprofitable", but unable to form a leakage-safe pool at all.
2. When forced to trade, it shows **no statistically significant edge** on a sample
   far too small to matter.
3. Benchmarks trade on ~10 events; nothing clears an honest event-clustered bar.
   The single "EDGE" flag is a tiny-sample favourite-buying artifact.
4. This is consistent with the literature (`RESEARCH_NOTES.md`): prices are
   well-calibrated (≈efficient) and skill rarely persists out-of-sample.

## Limitations (do not over-read)

- **Small sample:** only ~10 independent test *events* cleared the filters in 90d.
  This shows the strategy does not form/show edge **here**; it is **not** proof it
  fails everywhere. Politics (deeper, fewer retail) or a longer window may differ.
- Execution proxy has no order-book depth; fees were 0; single-price entry.
- Sports is the hardest case for copying (news-speed informed flow). A charitable
  category is a separate experiment (roadmap).

## Verdict

**INSUFFICIENT EVIDENCE (strong).** The first real-data pilot does not merely fail
to prove profitability — the leakage-safe strategy cannot form on Sports/90d, and
forced variants show no edge on a negligible sample. **Micro-live: NO-GO. Status:
PAPER-ONLY.** Next real step: repeat on Politics + a longer window, and calibrate
`consensus_score`, before any status change.

---

# Round 2 — relative decision bar + smaller stake

Three changes after round 1, run on the **same committed dataset log** (no new
API calls):

1. **Market-relative decision bar.** The absolute $100 floor was mis-calibrated:
   it discarded 95% of sports flow instead of filtering its noise. Replaced by
   the **p90 of each market's own trade-size distribution** (median floor here:
   **$5.69**), with a $10 hard dust guard.
2. **Smaller stake:** $5/trade instead of $30 (a $30 stake is also not fillable
   in these books).
3. **Dataset committed** as `data/real_sports_90d.json.gz` (484 KB) — replays
   cost zero API calls; the collector now skips the network when the log exists.

## Result (same walk-forward window, $1000 balance, $5/trade)

| min_resolved | strategy | n | events | paper P&L | ROI | 95% CI/share | verdict |
|---|---|---|---|---|---|---|---|
| 30 | **copy_strategy** | 0 | 0 | $0.00 | — | — | inert |
| 10 / 5 | **copy_strategy** | **10** | **2** | **+$1.02** | +2.0% | **[−inf, +inf]** | **no-edge** |
| any | majority | 47 | 10 | −$16.79 | −7.1% | [−0.076, +0.059] | no-edge |
| any | market_favorite | 49 | 10 | +$1.99 | +0.8% | [+0.016, +0.123] | "EDGE"* |
| any | random | 49 | 10 | −$73.63 | −30.1% | [−0.053, +0.085] | no-edge |

**The relative bar did wake the strategy up** — from 0 trades to 10 — but only
across **2 independent events**, which is not evidence of anything.

### A false-significance bug this run exposed (fixed)

At 2 events the bootstrap produced a **zero-width interval** `[+0.020, +0.020]`
and flagged **"EDGE"** — 100% win rate, apparently overwhelming significance,
from two correlated games. That is exactly the trap this harness exists to
prevent. Fixed: `MIN_EVENTS_FOR_CI = 8` — below that we return an infinite
interval and report `no-edge` rather than inventing confidence
(`test_ci_refuses_to_report_on_too_few_events`).

### Reading it honestly

- Copy strategy: **+$1.02 on 2 events** = noise, not edge. It still does not
  clear the `market_favorite` bar in any meaningful sense.
- `market_favorite` keeps its 96% win rate and **+0.8% ROI** — the favourite-buying
  trap in one line: near-perfect accuracy, almost no money.
- Nothing changed the verdict; the strategy is now *measurable* rather than inert,
  which is progress in instrumentation, not in profitability.

## Reproduce

```bash
uv run python -m src.backtest.collect   # no-op if the committed log exists
uv run python -m src.backtest.real      # tables above, deterministic from the log
```
