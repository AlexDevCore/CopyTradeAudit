# Research index

Start here. The project asked one question — *can you profit by following strong
Polymarket traders?* — and answered it honestly: **no measurable edge on the
available evidence.** These documents are the working record.

## Read in this order

| # | Document | What it establishes |
|---|---|---|
| 1 | [AUDIT_REPORT.md](AUDIT_REPORT.md) | Independent pre-live audit: architecture, data integrity, bugs ranked P0–P3, what was fixed |
| 2 | [RESEARCH_NOTES.md](RESEARCH_NOTES.md) | Live API validation + literature, each claim with source and date |
| 3 | [EXPERIMENTS.md](EXPERIMENTS.md) | Method and controlled synthetic validation — proves the harness finds edge when it exists and reports zero when it doesn't |
| 4 | [EXPERIMENTS_REAL.md](EXPERIMENTS_REAL.md) | First real-data pilot (Sports, 90d): strategy structurally inert |
| 5 | [EXPERIMENT_POLITICS.md](EXPERIMENT_POLITICS.md) | The charitable test (Politics, 365d, 109k trades) — the strongest evidence, and a methodology bug it exposed |
| 6 | [EXPERIMENT_TOPN_WINRATE.md](EXPERIMENT_TOPN_WINRATE.md) | "Follow the top win-rate traders, bet bigger" — tested and rejected, with the payoff maths |
| 7 | [EXPERIMENT_EXITS.md](EXPERIMENT_EXITS.md) | Early exits / stop-losses — changes risk shape, not edge |
| 8 | [EXPERIMENT_WEATHER.md](EXPERIMENT_WEATHER.md) | A forecasting-edge test; INCONCLUSIVE, blocked on resolution-source fidelity |
| 9 | [ROADMAP.md](ROADMAP.md) | Paths forward, Go/No-Go checklist, API cost |

Design decisions and architecture: [../DESIGN.md](../DESIGN.md)

## Headline numbers

- **370 markets · 134,000 trades · 46 independent events** across two categories.
- At entries above 0.95: copy-selected **+0.0200/share** vs blind price-band
  buying **+0.0211/share** — the tracked traders added nothing.
- A "top traders by win rate" book: **100% win rate, breakeven requires 96.3%**,
  one adverse event turns +$37 into −$537.
- Verdict: **INSUFFICIENT EVIDENCE**. Status: **PAPER-ONLY**, micro-live NO-GO.

## Four methodology bugs found in this project's own work

The reason to trust the negative result is that the same scrutiny was turned
inward:

1. **Timestamp units** — one API in seconds, another in milliseconds; unhandled,
   order books landed in the year 58,000.
2. **Degenerate bootstrap** — 2 events produced a zero-width interval flagged as
   `EDGE`. Fixed by `MIN_EVENTS_FOR_CI = 8`.
3. **Tail-blind bootstrap** — a book that had never recorded a loss returned a
   tight positive interval; an empirical bootstrap cannot see a tail it never
   sampled. Fixed by `Metrics.tail_blind`.
4. **Data-source mismatch** — a weather strategy lost 18 of 18 because the
   "ground truth" was a gridded reanalysis while the market settles on an airport
   station observation. Reported as INCONCLUSIVE rather than as a false negative.

## Reproduce

```bash
uv sync
uv run pytest -q                                        # 103 tests
uv run python -m src.backtest.experiments                # synthetic validation
uv run python -m src.backtest.real                       # sports pilot
uv run python -m src.backtest.real data/real_politics_365d.json.gz
```

Dataset logs are committed (`data/*.json.gz`), so every table above replays with
zero API calls.

## Scope discipline

No live trading, no private keys, no order placement, no geo-restriction
circumvention — by design, throughout. Everything here uses public read-only APIs.
