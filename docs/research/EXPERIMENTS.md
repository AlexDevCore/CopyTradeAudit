# EXPERIMENTS

**Scope honesty:** these experiments run on **controlled synthetic worlds** whose
ground truth is known. They validate that the harness measures correctly — they
are **not** evidence of profitability on real Polymarket data. No real backtest
exists yet (blocked on the data-pipeline items in `ROADMAP.md`).

## 1. Method

- **Leakage-safe as-of pool.** At a signal's detection time `t`, trader skill uses
  only markets **resolved strictly before `t`** (`backtest.as_of_skills`). Enforced
  by tests (`test_asof_excludes_markets_resolved_after_cutoff`,
  `test_peeking_would_inflate_the_sample`).
- **Walk-forward.** History accumulates as events resolve over time; the test
  window is the later portion (days 120–230 of a 220-event world), evaluated with
  pools built only from earlier-resolved events.
- **Metric.** Net **PnL per share** = `payoff(1/0) − entry_price − fee`. Win rate,
  profit factor, top-5 concentration reported alongside — never as the objective.
- **Uncertainty.** **Event-clustered** percentile bootstrap (resamples events, not
  trades), 2000 iterations, seed-fixed. Correlated markets in one event count as
  one observation → honest, wider intervals.
- **Benchmarks on identical signal points:** `random`, `always_yes`, `majority`
  (unweighted vote), `market_favorite` (buy the side priced > 0.5). `no_trade` = ∅.
  Exit rule = hold-to-resolution.

## 2. Synthetic worlds

`efficiency ∈ [0,1]` = how much the executable price reflects fair value
(`price(YES) = 0.5 + efficiency·(p_yes − 0.5)`). Traders: skilled (lean the true
favourite 85% of the time, buy near-fair), noise (random), favourite-buyers
(always the favourite but bought at 0.95 → high win rate, negative ROI). Reproduce:
`uv run python -m src.backtest.experiments`.

### Result — INEFFICIENT price (efficiency = 0.3)

| strategy | n | events | mean PnL/share | 95% CI (event-clustered) | verdict | win rate | PF |
|---|---|---|---|---|---|---|---|
| copy_strategy | 143 | 96 | **+0.1544** | [+0.064, +0.227] | **EDGE** | 0.73 | 2.00 |
| majority | 152 | 99 | +0.1497 | [+0.056, +0.213] | EDGE | 0.72 | 1.95 |
| **market_favorite** | 153 | 100 | **+0.1570** | [+0.065, +0.220] | **EDGE** | 0.73 | 2.02 |
| random | 153 | 100 | −0.0038 | [−0.084, +0.072] | no-edge | 0.50 | 0.98 |
| always_yes | 153 | 100 | −0.0116 | [−0.098, +0.066] | no-edge | 0.50 | 0.95 |

### Result — EFFICIENT price (efficiency = 1.0)

| strategy | n | events | mean PnL/share | 95% CI | verdict | win rate | PF |
|---|---|---|---|---|---|---|---|
| copy_strategy | 140 | 97 | −0.0071 | [−0.101, +0.062] | no-edge | **0.72** | 0.96 |
| majority | 152 | 99 | −0.0230 | [−0.114, +0.038] | no-edge | 0.72 | 0.89 |
| market_favorite | 153 | 100 | −0.0180 | [−0.110, +0.045] | no-edge | 0.73 | 0.91 |
| random | 153 | 100 | −0.0049 | [−0.075, +0.080] | no-edge | 0.50 | 0.97 |

## 3. What the numbers actually say

1. **The harness works.** It finds a real edge when one exists (inefficient world,
   CI excludes 0) and reports **no edge** when the market is efficient (all CIs
   include 0). It does not manufacture significance.
2. **Win rate ≠ profit.** In the efficient world `copy_strategy` still wins **72%**
   of trades but nets **~0**. Selecting or bragging on win rate would be a trap.
3. **Copying adds no unique edge here.** When an edge exists it comes from **price
   inefficiency**, and the dumb `market_favorite` benchmark (just buy the
   higher-priced side, no traders at all) captures **the same** +0.157. So in this
   world, trader-copying provides nothing over reading the price. Any real result
   must beat `market_favorite`, not just `no_trade`.
4. This mirrors the literature: real Polymarket prices are well-calibrated
   (≈efficient), which is the regime where copy edge → 0 (`RESEARCH_NOTES.md` §C).

## 4. Accepted / rejected

| Change | Decision | Basis |
|---|---|---|
| Leakage-safe as-of pool | **ACCEPT** | Correctness prerequisite; test-enforced |
| Event-clustered CI (vs per-trade) | **ACCEPT** | Per-trade CIs overstate significance on correlated markets (`test_event_clustering_widens_ci_vs_naive`) |
| ROI floor to exclude favourite-buyers (P1-5) | **ACCEPT** | `test_select_pool_excludes_favourite_buyer` |
| ms/seconds timestamp fix (P0-2) | **ACCEPT** | Live-schema test |
| "copy traders beats reading price" | **REJECT (unproven)** | `market_favorite` matched `copy_strategy` in synthetic; needs real data to revisit |
| Any profitability claim on real markets | **INSUFFICIENT EVIDENCE** | No real backtest yet |

## 5. Limitations

- Synthetic ≠ real. Real order-book depth, latency distribution, resolution
  disputes, fees-when-enabled, and adversarial reflexivity are not modelled.
- Execution here uses a single executable price + constant slippage; real runs must
  walk live L2 depth (the paper engine already can — it is not yet fed real books).
- No calibration of `consensus_score` to empirical probability (audit P1-1).

## 6. Reproduce

```bash
cd "CopyTrader - v0.0"
uv sync
uv run pytest -q                         # full suite (98 tests)
uv run python -m src.backtest.experiments  # the tables above (seed-fixed)
```
