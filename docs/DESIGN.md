# CopyTradeAudit — Design (v1.0)

Living document. Records agreed decisions, architecture, starting parameters and
open questions. Updated as the project develops.

## Hypothesis

Can you make money by following the public decisions of historically successful
Polymarket traders, once you honestly account for entry price, detection
latency, liquidity, fees, slippage and position changes? The system's primary
allowed answer is **NO TRADE**.

## Agreed decisions

| Area | Decision |
|---|---|
| Jurisdiction | US — **paper trading only**. Live trading via VPN is explicitly out of scope: Polymarket's international venue has been geoblocked for US IPs since the 2022 CFTC settlement, and circumventing that is a regulatory risk we do not take. See `docs/research/RESEARCH_NOTES.md`. |
| Categories | Politics + Sports (category-agnostic architecture; ingest starts with politics) |
| v1 mode | Paper only + empty stub interfaces for live behind a disabled flag |
| Virtual balance | $1,000 |
| History depth | 180 days |
| Poll frequency | ~90 s polling = realistic detection latency |
| Min trader sample | ≥30 resolved independent markets per category |
| Market selection | Binary YES/NO + minimum liquidity filter |
| Win/loss point | Net exposure at resolution; early exit tracked as a separate metric |
| Decision threshold | Both: minimum $ **and** a fraction of the trader's typical size |
| Reversal | A separate new decision (the old one closes as REVERSED) |
| Maker/taker | Classified; maker/unknown does **not** signal by default |
| Bet size | Fixed fraction of balance (3%, capped at 5% per position) |
| Limits | Per position + per correlated group (10% per event) |
| Exit | Rule-based; hold-to-resolution always logged as a control |
| Entry gate | Positive edge after costs + minimum consensus score, otherwise NO TRADE |
| Trader pool | Leaderboard ∪ holders of eligible markets, then filtered by sample size |
| Interface | Local web dashboard (FastAPI), localhost only |
| Confirmations | Paper — automatic + full audit trail; manual confirmation reserved for live |
| Stack | Python (uv, src/, pytest) |

## Defining "one independent decision"

- Unit = `wallet + market`. Direction = the sign of **net exposure**
  (YES-equivalent), not individual trades.
- Everything normalises to YES-equivalent: buying NO = selling YES,
  NO@p = YES@(1−p).
- Adding to the same side → same forecast (raises conviction/size, not the count).
- Net sign flip → the old decision closes (REVERSED) + a new decision opens.
- Reduction without a sign change → the decision stays OPEN (not a forecast against).
- Net returning to ~0 → CLOSED (early exit, excluded from held-to-resolution win rate).
- Dust below both thresholds never becomes a decision.

Implementation: `src/normalize/decisions.py` (`build_decisions`, `decision_correct`).

## Scoring

- Raw win rate is displayed, but **ranking** uses the lower bound of the Wilson
  interval.
- Only decisions that survived to resolution (held-to-resolution) are counted.
- Verified by test: 9/10 does not rank above 160/200.

Implementation: `src/scoring/winrate.py`.

## Execution simulation

- Walks real order-book depth outward from the best price.
- Never a midpoint or a single convenient price.
- Partial fills when depth is insufficient; fees on traded notional (pulled
  per-market from CLOB, **not hardcoded**); slippage = avg − ref.

Implementation: `src/paper/execution.py` (`simulate_buy`, `simulate_sell`).

## Architecture

```
src/
  ingest/     # Gamma / Data / CLOB clients + polling — the ONLY place with network access
  store/      # SQLite: raw_* (pre-normalisation) + normalised state
  normalize/  # trades -> net exposure -> decisions
  scoring/    # Wilson / win rate, walk-forward (no future data)
  signal/     # consensus score, edge-after-costs, NO TRADE gate
  paper/      # execution simulation
  risk/       # position / correlated-group limits, staleness, kill switch (stub)
  audit/      # decision journal + strategy rule version
  web/        # FastAPI + light frontend (5 screens)
  live/       # EMPTY stubs, feature flag OFF. No order logic
```

The core (`normalize/scoring/signal/paper/risk`) is pure functions, tested
offline with no network. Walk-forward principle: the score and the pool at each
decision point are computed only from data known **before** that moment.

## Starting parameters

See `src/domain/params.py` (`StrategyParams`). All values are starting points,
tunable via config:

- min_notional_usd=$100, min_fraction_of_typical=0.25
- min_resolved_markets=30, history_days=180
- poll_interval_sec=90, reaction_latency_sec=5, data_staleness_sec=300
- starting_balance_usd=$1000, bet_fraction=3%, max_position=5%, max_group=10%
- consensus_threshold=0.60, min_edge_after_costs=0.02, wilson_z=1.96

## Phases

- **A (done):** deterministic core + tests — decisions, scoring, execution.
- **B (done):** ingest clients (Gamma/Data/CLOB, injectable network, 2026 API /
  CLOB V2), parsers (raw→domain), store (SQLite: raw before normalisation +
  app_state, survives restart), deterministic fixture replay.
- **C (done):** signal (consensus + residual edge-after-costs + NO TRADE) + risk
  (limits/staleness). Three fixes shipped: price-aware selection (`skill.py`,
  ROI floor), residual edge against our own price, out-of-sample validation
  (`validation.py`).
- **D (done):** paper portfolio (sizing, rule-based exits + hold-to-resolution
  control branch, full audit record), audit log + `audit_events` table, state
  persistence across restarts.
- **E (done):** web dashboard (Dashboard / Markets / Traders / Paper portfolio /
  Audit).

103 tests, all green.

## Open questions

- Wallet independence: v1 uses a light co-trading heuristic + a flag; full
  clustering of related addresses is deferred.
- Calibrating consensus score → probability: only after enough history accrues.
- Exact fee source and order-book parameters — to be confirmed against current
  CLOB documentation.
- Market category classification (Gamma tags) — mapping to be confirmed against
  real data.
