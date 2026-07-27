# CopyTradeAudit — v1.0

A research engine built to test one honest hypothesis:

> Can you make money by following the public decisions of historically
> successful Polymarket traders, once you account for the real entry price,
> detection latency, liquidity, fees, slippage and position changes?

**This is not a profit claim.** The system's primary allowed answer is `NO TRADE`.

## Verdict: the hypothesis is disconfirmed

Measured on public data — 370 markets, ~134,000 trades, 46 independent events:

- **Copying adds nothing over reading the price.** Above 0.95, copy-selected
  trades returned +0.0200 per share. Buying that same price band blindly, with
  no traders involved at all, returned +0.0211.
- Of 38 politics traders with ≥30 resolved decisions, only 2 clear a 2% ROI bar.
- Three follow-up strategies (top-N by win rate, ROI ranking with a price cap,
  early exits and stop losses) were tested and rejected. Ranking traders by win
  rate does not find skill — it finds people who buy near-certainties at 98¢.

Final status: **INSUFFICIENT EVIDENCE, paper-only, micro-live NO-GO.**

Full write-ups in [`docs/research/`](docs/research/) — `AUDIT_REPORT.md` first.

## Four methodology bugs found in my own work

The most useful part of the project. Each one produced a confident but wrong
positive result:

1. **Unit mismatch.** One endpoint returns timestamps in milliseconds, another
   in seconds. Unhandled, order books landed in the year 58,000.
2. **Bootstrap over 2 events** returned a zero-width confidence interval and
   flagged `EDGE` — fake significance manufactured from two correlated games.
   Fixed by `MIN_EVENTS_FOR_CI = 8`.
3. **`tail_blind`.** Books of near-certainties that never recorded a single loss
   produced tight, confident, positive intervals. An empirical bootstrap
   resamples only outcomes that *occurred*, so with zero observed losses it
   cannot see the −0.98 tail. The engine now refuses to certify an edge when
   there are no losses **and** mean entry price ≥ 0.90.
4. **Broken ground truth.** A weather strategy lost 18 of 18 bets. The cause was
   not the model: these markets settle on a specific airport station, and the
   comparison used a gridded reanalysis that understates daily maxima by ~1°C.
   Reported as INCONCLUSIVE rather than published as a false negative.

## Method

- **Leakage-safe scoring.** At any signal, a trader's skill is computed only
  from markets that resolved *before* that moment. As-of pools, walk-forward.
- **Event-clustered bootstrap CIs.** 50 correlated markets inside one event
  count as one observation, not fifty.
- **Order-book execution simulation.** Walks real depth outward from the best
  price, with fees pulled per-market from CLOB (never hardcoded), slippage and
  partial fills. Never assumes a midpoint fill.
- **Relative decision threshold.** A percentile of the market's own trade sizes
  rather than a fixed dollar floor — an absolute $100 threshold discarded 95%
  of sports activity.

## Scope and safety

Strictly paper trading — a simulation with no real money. There is no live
mode; only empty stub interfaces behind a disabled feature flag. **No wallet
private keys and no exchange credentials are used, stored or required.**

Datasets under `data/*.json.gz` are committed so past events replay without
re-hitting the API. All sources are public, read-only endpoints.

## Install

Requires [`uv`](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync
```

## Tests

```bash
uv run pytest -q
```

103 tests, all green.

## Run

```bash
uv run python -m src.main
```

## Layout

```
src/
  ingest/     # Gamma / Data / CLOB clients + polling — the only place with network access
  store/      # SQLite: raw_* (pre-normalisation) + normalised state
  normalize/  # trades -> net exposure -> decisions
  scoring/    # Wilson / win rate, walk-forward scoring with no future data
  signal/     # consensus score, edge-after-costs, NO TRADE gate
  paper/      # execution simulation and portfolio
  risk/       # position and correlated-group limits, staleness, kill switch
  audit/      # decision journal + strategy rule version
  web/        # FastAPI dashboard, localhost only
  live/       # EMPTY stubs, feature flag OFF. No order logic whatsoever
```

Design decisions and parameters: [`docs/DESIGN.md`](docs/DESIGN.md).
