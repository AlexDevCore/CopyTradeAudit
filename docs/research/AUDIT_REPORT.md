# AUDIT_REPORT — CopyTrader pre-live audit

_Independent pre-live audit. Goal: try to DISPROVE profitability, not confirm it.
Real-money trading, private keys, and order placement are out of scope by mandate._

Date of audit: 2026-07-24 · Baseline commit: `2c28a8d` (v0.0) · Tests at audit end: **98 passed**.

## 1. Current state

Deterministic research core + local read-only dashboard, phases A–E:
`ingest` (Gamma/Data/CLOB clients, network injectable) → `store` (SQLite, raw kept
verbatim + app_state) → `normalize` (net-exposure decisions) → `scoring`
(Wilson + price-aware ROI) → `signal` (consensus + residual-edge gate + NO_TRADE)
→ `risk` (limits/staleness) → `paper` (order-book execution, portfolio, exit vs
hold-to-resolution, audit) → `web`. New in this audit: `backtest` (leakage-safe
harness + event-clustered CI + benchmarks + synthetic worlds).

No live trading, no keys, no order placement. State survives restart (tested).

## 2. Architecture assessment

| Question | Verdict |
|---|---|
| Data / storage / strategy / execution / UI separated? | **Yes** — clean module boundaries |
| Strategy testable without network? | **Yes** — core is pure; 98 offline tests |
| Decision reproducible from stored data? | **Partial** — raw stored; deterministic replay exists; full audit-from-store path not yet wired end-to-end |
| Business logic inside UI? | **No** — `web/service.py` is a pure view layer |
| State lost on restart? | **No** — portfolio + audit persist (tested) |
| Strategy versioning? | **Yes** — `strategy_version` stamped on every trade |
| Old vs new strategy on same data? | **Yes now** — `backtest.run_benchmark` compares on identical signal points |

Architecture is sound and not over-abstracted. No microservice sprawl. No changes needed here.

## 3. Findings (P0 = correctness/leakage/dangerous finance … P3 = cosmetic)

| ID | Sev | Finding | Evidence | Status |
|---|---|---|---|---|
| P0-1 | P0 | No **enforced** look-ahead protection in scoring primitives; any backtest built on them could trivially use future outcomes to pick the pool. | Scoring took `outcomes` with no as-of filter. | **FIXED** — `backtest.as_of_skills` only counts markets **resolved strictly before** the signal time; enforced by `test_asof_excludes_markets_resolved_after_cutoff` + leakage-inflation test. |
| P0-2 | P0 | **Timestamp unit mixing.** Data `/trades` is seconds (10 digits) but CLOB `/book` is **milliseconds** (13 digits); the parser treated any digit string as seconds → book timestamps landed in year ~58000. | Live payloads (2026-07): trade ts `1784943456`, book ts `"1784943842216"`. | **FIXED** — `_epoch_to_dt` auto-detects ms (≥1e12); pinned by `test_live_book_millisecond_timestamp_and_best_prices`. |
| P1-1 | P1 | **`consensus_score` is treated as a probability** in the edge/`NO_TRADE` gate (`edge = score − price − fee`) although it is explicitly uncalibrated. The whole trade/no-trade decision rests on an unvalidated score→probability mapping. | `signal/engine.py`, `paper/cycle.py`. | **DOCUMENTED (limitation).** Must remain PAPER-ONLY until the score is empirically calibrated (Brier/reliability curve). This is the single biggest reason micro-live is NO-GO. |
| P1-2 | P1 | **maker/taker gate is non-functional on real data.** The public `/trades` payload carries **no** maker/taker flag; `is_taker` is always `None`, and `takerOnly=true` returned identical rows to the default. | Live `/trades` keys contain no taker field; `test_live_trade_has_no_maker_taker_flag`. | **DOCUMENTED.** Cannot separate taker aggression from maker fills from this feed. Options (roadmap): infer role from on-chain fill data, or treat `/trades` per endpoint semantics after verifying them. Do **not** claim maker/taker filtering works. |
| P1-3 | P1 | **Pool-discovery endpoint wrong.** `GET /leaderboard` on `data-api` returns **404**. | Live call 404. | **DOCUMENTED.** Discovery must use holders/on-chain or the correct (re-verified) leaderboard surface before any real pool is built. |
| P1-4 | P1 | **Fees not parsed and must not be hard-coded.** `/fee-rate` returns `{"base_fee": 0}` (field name + current value), which the client never parses; demo used a hard-coded 0.01. | Live `/fee-rate`. | **DOCUMENTED.** Execution must read `base_fee` per market at run time (fees may be enabled later; Gamma exposes `feesEnabled`/`feeType`). |
| P1-5 | P1 | **`min_mean_roi` defaulted to 0.0**, so fix (a) (excluding favourite-buyers) was off by default — a 98%-win-rate favourite-buyer could enter the pool. | `params.py`. | **FIXED** — default raised to `0.02`; `select_pool` enforces it; `test_select_pool_excludes_favourite_buyer`. |
| P1-6 | P1 | **Drawdown under-measured** — `max_drawdown` only moved when `equity()` was called explicitly; a run that never marked would report ~0 drawdown. | `portfolio.py`. | **FIXED** — `_touch_equity()` records (entry-priced, conservative) equity on every open/exit/resolve. |
| P1-7 | P1 | **No wallet-independence detection.** `min_signal_contributors=2` can be satisfied by two wallets of one entity (Sybil / co-trading), double-counting a single opinion. | Design gap. | **OPEN.** Needs a co-trading/cluster heuristic before consensus is trustworthy. |
| P1-8 | P1 | **Decision open/closed state depends on complete per-(wallet,market) history.** A pagination gap makes a closed position look open (or vice versa), corrupting held-to-resolution scoring. | `normalize/decisions.py` semantics. | **OPEN.** Ingest must guarantee completeness (cursor to exhaustion + gap detection) before scoring a trader. |
| P2-1 | P2 | **negRisk multi-outcome markets** not modelled (treated as plain binary). | Gamma `negRisk`/`negRiskMarketID`. | OPEN. |
| P2-2 | P2 | **Correlated-group is manual** (`group_id` passed in); no auto-grouping by `event_id`/`negRiskMarketID`, so correlated exposure can be missed. | `risk`/`portfolio`. | OPEN (harness already clusters by `event_id` for stats). |
| P2-3 | P2 | Raw-trade dedup relies on stable JSON; enrichment fields could defeat it. Prefer `transactionHash`. | `store/db.py`. | OPEN. |
| P3-1 | P3 | Reversal entry-price uses the flip trade's price for the whole residual (minor approximation). | `normalize/decisions.py`. | Documented. |
| P3-2 | P3 | `StarletteDeprecationWarning` (httpx TestClient). | Test warning. | Cosmetic. |

## 4. Data-integrity checklist (audited against live payloads)

- **Timezones/units:** trades = unix **seconds** UTC; book = **milliseconds** UTC — now handled (P0-2).
- **YES/NO split:** normalised to signed YES-equivalent; `No@p == Yes@(1−p)` (validated on a real `outcome:"No"` row).
- **BUY/SELL:** both appear; mapped to signed net exposure. **SPLIT/MERGE/REDEEM are not in `/trades`** (they are on-chain CTF ops) → currently invisible; flagged as a data-completeness gap (affects net-exposure reconstruction).
- **Order book:** `asks` come **descending** from the API; our re-sort to ascending is the correct defensive behaviour (validated).
- **Resolution:** derivable from Gamma `outcomePrices` + `closed`/`umaResolutionStatuses`; not yet wired into ingest.
- **Duplicates / pagination / reconnect:** raw store dedups; cursor-exhaustion + gap detection **not yet implemented** (P1-8).

## 5. What was changed in this audit

1. **P0-2 fixed** — ms/seconds auto-detection in timestamp parsing (+ live-schema tests).
2. **P0-1 addressed** — leakage-safe `backtest` harness: as-of pool, event-clustered bootstrap CI, benchmark suite, synthetic worlds; 10 harness tests.
3. **P1-5 fixed** — `min_mean_roi` default 0.02 + enforced `select_pool`.
4. **P1-6 fixed** — drawdown now updates on every portfolio state change.
5. Live read-only API validation captured and pinned as tests (schema drift guard).

Net: **86 → 98 tests**, all green. No refactor of working code; changes are surgical.

## 6. What remains (not fixed on purpose)

P1-1 (calibration), P1-2 (maker/taker data source), P1-3 (discovery endpoint),
P1-4 (fee parsing), P1-7 (wallet independence), P1-8 (history completeness),
plus P2 items. These are prerequisites for any *real*-data claim and are tracked
in `ROADMAP.md`. None can be closed with synthetic data.

## 7. Honest bottom line

The **engineering** is in good shape and now measures itself honestly. The
**strategy is unproven on real data**: there is no real out-of-sample result, the
consensus score is uncalibrated, copyability is not demonstrated, and independent
research (see `RESEARCH_NOTES.md`) shows trader skill on Polymarket rarely
persists out-of-sample. Verdict for the strategy: **INSUFFICIENT EVIDENCE.**
Go/No-Go for micro-live: **NO-GO** (see `ROADMAP.md` → PAPER-ONLY).
