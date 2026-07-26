# Experiment — Politics, 365 days (the charitable test)

Sports was the hardest case for copying (news-speed informed flow, retail micro
bets). Politics is the most favourable venue left: deeper books, slower
information, more repeat traders. This is the test the hypothesis deserved.

Data: **250 markets · 109,572 trades · 12,607 wallets**, 365 days, public
read-only API, committed as `data/real_politics_365d.json.gz`.
Reproduce: `uv run python -m src.backtest.real data/real_politics_365d.json.gz`

## 1. The pool finally forms — and then collapses on ROI

Unlike sports, politics has traders with real track records:

| traders with ≥N resolved decisions | count |
|---|---|
| ≥3 | 463 |
| ≥10 | 136 |
| ≥30 | **38** |
| ≥50 | 25 |

(In sports the maximum was 28 decisions and **zero** traders cleared 30.)

But applying the price-aware floor:

| pool | ROI floor ≥0.02 | no ROI floor |
|---|---|---|
| min_resolved=30 | **2 traders** | 38 |
| min_resolved=10 | 28 | 136 |

**Of the 38 traders with substantial, resolved track records, only 2 have a mean
ROI above 2%.** That is the headline: experience is common, price-aware edge is
not. With a 2-trader pool the consensus rule almost never fires (0–3 trades).

## 2. Benchmarks — now with real statistical power (36–38 events)

| benchmark | n | events | P&L @$25 | ROI | win rate | 95% CI/share | verdict |
|---|---|---|---|---|---|---|---|
| majority | 118 | 36 | −$62.71 | −2.1% | 0.75 | [−0.137, +0.046] | no-edge |
| **market_favorite** | 123 | **38** | **−$15.07** | **−0.5%** | 0.90 | [−0.137, +0.037] | **no-edge** |
| random | 123 | 38 | −$1047.58 | −34.1% | 0.54 | [−0.166, +0.024] | no-edge |

**This retires the sports "EDGE".** `market_favorite` looked significant on 10
sports events (+0.8%); across 38 politics events it is **negative** (−0.5%). The
sports result was an upset-free small-sample artifact, exactly as suspected.

## 3. A methodology bug this run exposed (fixed)

Five copy variants flagged **EDGE** with tight positive intervals:

| variant | n | events | avg entry | win rate | CI/share |
|---|---|---|---|---|---|
| copy, min_resolved=10, no ROI floor | 36 | 12 | 0.973 | **1.00** | [+0.024, +0.056] |
| top20 rank=wilson | 30 | 9 | 0.978 | 1.00 | [+0.020, +0.040] |
| top50 rank=wilson | 35 | 11 | 0.975 | 1.00 | [+0.020, +0.048] |
| top50 rank=win rate | 19 | 10 | 0.966 | 1.00 | [+0.025, +0.062] |
| top50 rank=ROI | 9 | 8 | 0.957 | 1.00 | [+0.026, +0.070] |

All of them are **near-certainty books that won every single trade**. An
empirical bootstrap resamples only outcomes that *occurred* — with zero observed
losses it cannot see the −0.98/share tail, so it returns a tight, confident,
**wrong** interval.

Fixed: `Metrics.tail_blind` — when a book has **no observed losses and a mean
entry ≥0.90**, `ci_excludes_zero` returns False. We refuse to certify an edge the
sample is structurally incapable of testing. All five now report
`TAIL-BLIND` instead of `EDGE`.

## 4. Is the copy selection actually better than the price?

Base-rate comparison in the same window:

| entry band | copy: n | copy: win rate | copy mean/sh | all positions: n | win rate | mean/sh |
|---|---|---|---|---|---|---|
| 0.95–1.01 | 32 | 1.00 | +0.0200 | 89 | 0.97 | −0.0115 |
| 0.90–0.95 | 4 | 1.00 | +0.0857 | 7 | 1.00 | +0.0776 |
| below 0.90 | 0 | — | — | 150 | 0.20 | −0.0043 |

Copy did avoid the ~3% of favourites that lost. Is that skill?

> At an average entry of 0.980, expected losses over 32 trades = **0.6**.
> **P(all 32 win) = 0.52.**

Observing 32/32 is a **coin flip**, not evidence. And note the copy strategy never
entered below 0.90 at all — it is structurally a favourite-buying book.

## Verdict

**The charitable test did not rescue the hypothesis.**

- Politics does produce traders with real track records — but **only 2 of 38 clear
  a 2% ROI bar**, so a price-aware pool barely exists.
- With enough events to measure properly, **every benchmark is negative**, and the
  sports "edge" is gone.
- Every copy variant that looked profitable is a 97¢ book whose perfect record is
  statistically unremarkable and whose downside the sample cannot even see.

Combined with sports, the conclusion across **370 markets, 134k trades, 46
independent events**: **late copying of public Polymarket signals shows no
measurable edge over reading the price.** Status unchanged: **PAPER-ONLY,
micro-live NO-GO**, and the honest label for the strategy family is now closer to
*disconfirmed on available evidence* than to *untested*.
