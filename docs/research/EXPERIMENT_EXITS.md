# Experiment — "enter at mid odds, cut when defeat looks likely"

Tested proposal: enter around ~0.70 rather than 0.98, stay while the position
goes your way, and **cut early when defeat approaches**, recovering part of the
stake instead of losing all of it.

Code: `src/backtest/exits.py` · data: committed real sports log.

## The question that actually decides it

"Getting part of the money back" feels like a saving, but it is only a saving if
the exit price is **better than what the position is truly worth**. So the test
is not whether cutting feels prudent — it is:

> conditional on the price having fallen to X, how often does the position still win?

If markets are calibrated, a position now priced X wins about X of the time. The
drop is information **already in the price**, so selling at X is a fair trade, not
a rescue — and you pay the spread twice for the privilege.

## 1. Calibration after a drop

Among positions that traded down to each level (both sides of every market, so
the sample is not conditioned on any strategy):

| fell to | n | observed win rate | if calibrated | reading |
|---|---|---|---|---|
| 0.60 | 3 | 0.67 | 0.60 | fair |
| 0.50 | 4 | 0.50 | 0.50 | fair |
| 0.40 | 5 | 0.60 | 0.40 | cutting would have cost |
| 0.30 | 4 | 0.25 | 0.30 | fair |
| 0.20 | 5 | 0.00 | 0.20 | cutting would have saved |
| 0.10 | 9 | 0.00 | 0.10 | fair |

**Samples are tiny (3–9).** No level shows a reliable gap between the observed
win rate and the price. Directionally: the market is roughly calibrated after a
drop, and any advantage only appears deep underwater (≤0.20) where there is
little left to save.

## 2. Stop-losses priced on every position (n=234, 28 events)

Dollar totals are misleading here — equal-dollar sizing buys far more shares of
cheap sides — so the honest column is **PnL per share**:

| exit rule | mean PnL/share | win rate |
|---|---|---|
| **hold to resolution** | **−0.0058** | 0.50 |
| stop at 0.70 | −0.0686 | 0.37 |
| stop at 0.60 | −0.0704 | 0.38 |
| stop at 0.50 | −0.0600 | 0.41 |
| stop at 0.40 | −0.0315 | 0.48 |
| stop at 0.30 | −0.0380 | 0.47 |
| stop at 0.20 | −0.0148 | 0.50 |

**Every stop-loss level performed worse than simply holding.** The closer the
stop, the worse the result.

Why: a stop at 0.50 **fired on 152 positions, of which 38 (25%) went on to win**.
Those are wins converted into realised losses.

## 3. The exit does not fill where you think

| stop trigger | actual observed fill |
|---|---|
| 0.50 | median **0.080**, mean 0.176 |
| | 119/152 filled below 0.40 · 94/152 below 0.20 |

You intend to sell at 0.50 and in this data you get ~0.18.

**Honest limitation:** the price path here is reconstructed from *trade prints*,
which are sparse in thin sports markets, so part of this gap is measurement
resolution rather than pure market gapping. A real resting stop might fill closer
to the trigger. The direction of the effect is real (thin books gap), the
magnitude is overstated by the proxy.

## Verdict

**It changes the risk shape, not the edge.**

- Cutting does not create money. You sell at a price that already reflects the
  reduced chance of winning; the market pays fair value for what remains. That is
  variance reduction, not expected-value improvement — and it costs the spread twice.
- Measured here, every stop level **underperformed holding**, mainly by destroying
  the 25% of drawn-down positions that recovered.
- It cannot rescue the favourite-buying book either: at a 0.98 entry there is 2¢
  of upside against 98¢ of risk, so no exit rule fixes that geometry.

Where the idea is genuinely right: a stop **caps catastrophic single-event loss**.
That is a real benefit for survivability — but it is a risk-management choice paid
for out of returns, not a source of profit, and it does not turn a no-edge
strategy into a profitable one.

## Reproduce

```bash
# calibration + stop-loss pricing
python -c "from src.backtest.exits import collect_touches, apply_stop_loss"
```
