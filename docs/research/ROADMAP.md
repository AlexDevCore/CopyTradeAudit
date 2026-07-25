# ROADMAP + Go/No-Go

No fabricated dates. Effort is relative (S/M/L). "Evidence to advance" is the gate,
not a calendar.

## Paths

### 1. Research terminal (read-only)
- **Value:** high — turns the free public data into a real trader/market analytics
  tool even if no strategy ever trades.
- **Effort:** M. **Risk:** low.
- **Depends on:** correct discovery endpoint (P1-3), history completeness (P1-8).
- **Evidence to advance:** none needed — it is read-only research.

### 2. Improved paper engine on REAL data
- **Value:** high — the prerequisite for any honest claim. Feed the paper engine
  and the backtest harness with real trades, real resolutions, and real L2 books.
- **Effort:** L. **Risk:** medium (data completeness, dispute handling).
- **Depends on:** P1-2 (maker/taker source), P1-3, P1-4 (fee parse), P1-8
  (pagination/gap detection), SPLIT/MERGE/REDEEM handling, negRisk (P2-1).
- **Evidence to advance:** deterministic real-data replay reproduces identical
  decisions twice; execution walks real book depth.

### 3. Live **signals** without execution
- **Value:** medium — surface NO_TRADE/BUY suggestions with explanations; measure
  calibration of `consensus_score` against realised outcomes over time.
- **Effort:** M. **Risk:** low (no orders).
- **Depends on:** path 2; a calibration harness (Brier/reliability curve).
- **Evidence to advance:** a reliability curve showing the score tracks empirical
  frequency (fixes P1-1) before the score is ever called a probability.

### 4. Guarded micro-live ($20–50, manual confirm)
- **Value:** speculative — only worth it if paths 2–3 produce out-of-sample edge
  that survives costs and beats `market_favorite`.
- **Effort:** L. **Risk:** high (regulatory + financial).
- **Depends on:** the Go/No-Go checklist below **fully green**; lawful venue
  (Polymarket US, when available — **not** VPN); CLOB V2 signing; kill-switch,
  heartbeat, cancel-on-disconnect, geoblock check, separate hot wallet.
- **Evidence to advance:** positive **untouched** out-of-sample net result, stable
  across ≥2 time windows, not driven by a few outliers.

### 5. Further (only if justified)
- Cross-platform signals, order-book microstructure models, auto-calibrated sizing
  (fractional Kelly **only after** calibration is proven). Not before path 4.

## Recommended order

1 and 2 in parallel → 3 → (gate) → 4. Do **not** skip calibration (3) on the way
to 4.

## API cost per day

The strategy's data is the **public, keyless Polymarket APIs → $0.00/day.**

- Polling at 90s = **960 cycles/day**. A generous per-cycle budget (≈1–3 Data
  `/trades`, up to ~20 CLOB `/book` or one batched `/books`, occasional Gamma
  `/markets`) ≈ **~24,000 requests/day**.
- Rate-limit headroom (Cloudflare per-10s → per-day): Data `/trades` 200/10s ≈
  1.73M/day; CLOB `/book` 1500/10s ≈ 12.9M/day. Usage is **<2%** of the tightest
  cap. No paid tier exists — cost is **$0**, the constraint is rate limits, not money.
- **Optional** LLM explanations (audit report text only, **off by default, never in
  the trading loop**): a few tens of small Claude Haiku calls/day would cost on the
  order of **cents/day**; **$0** when disabled.
- Hosting (if run on a VPS instead of locally) is an infra cost, not an API cost.

**Daily API spend for the system as specified: ≈ $0.00** (public data is free).

## Go / No-Go checklist for future micro-live

| Requirement | State |
|---|---|
| Positive untouched out-of-sample net result after costs | ❌ no real backtest yet |
| Result not driven by a few outliers (top-5 share checked) | ❌ n/a |
| Enough independent **events** (not trades) | ❌ n/a |
| Stable across ≥2 time windows | ❌ n/a |
| Measured or conservatively modelled latency | ⚠️ modelled only |
| Verified order-book simulation on real L2 | ⚠️ engine ready, not fed real books |
| `consensus_score` calibrated to probability | ❌ uncalibrated (P1-1) |
| maker/taker signal validated | ❌ no data source (P1-2) |
| Risk limits (position/day/drawdown) | ✅ implemented |
| Correlation limits | ⚠️ manual grouping only (P2-2) |
| Data-freshness guard | ✅ staleness → NO_TRADE |
| Kill switch / heartbeat / cancel-on-disconnect | ❌ live-only, not built (by design) |
| Separate hot wallet, ≤ $20–50, no withdrawal in UI | ❌ live-only, not built |
| Manual confirm of each real trade | ❌ live-only, not built |
| Geoblock check / lawful venue | ❌ (US → Polymarket US only, when available) |
| Full decision audit log | ✅ implemented |
| Rollback / auto-stop conditions | ⚠️ partial (staleness stop; no full kill switch) |

## Final status

**PAPER-ONLY.**  Micro-live: **NO-GO.**

The engineering is sound and now self-measuring, but there is **no real
out-of-sample evidence of edge**, the consensus score is uncalibrated, copyability
is undemonstrated, and independent research shows Polymarket skill rarely persists
out-of-sample. Advance to **READY FOR EXTENDED PAPER TEST** only after path 2
(real-data replay) + path 3 (calibration) are done and a real, event-clustered,
out-of-sample result beats `market_favorite` after costs. Do not grant micro-live
status on the strength of any backtest alone.
