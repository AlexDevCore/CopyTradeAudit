# RESEARCH_NOTES

Checked: 2026-07-24. Each item: source · date · impact on the project.
Live API facts are from direct read-only calls (most authoritative); the rest
from the sources listed. Preprints are marked as such.

## A. Live API validation (direct read-only calls, 2026-07-24)

Captured actual payloads from the public, keyless endpoints.

- **Data `/trades`** (`https://data-api.polymarket.com/trades`) — fields:
  `proxyWallet, side (BUY/SELL), asset, conditionId, size, price, timestamp,
  outcome (Yes/No), outcomeIndex, transactionHash, …`.
  - `timestamp` is **unix seconds** (10 digits).
  - **No maker/taker field.** `takerOnly=true` returned identical rows to the
    default. → *Impact:* maker/taker filtering is not possible from this feed
    (audit P1-2). `outcomeIndex` was `999` (sentinel) — rely on the `outcome`
    string (we do).
- **CLOB `/book`** (`https://clob.polymarket.com/book?token_id=…`) — `asks`/`bids`
  are `{price,size}` **strings**; `asks` returned **descending**; `timestamp` is
  **milliseconds** (13 digits), plus `tick_size`, `min_order_size`, `neg_risk`.
  → *Impact:* fixed the ms/seconds bug (P0-2); our ascending re-sort is correct.
- **CLOB `/fee-rate`** — returns `{"base_fee": 0}`. → *Impact:* fees are currently
  0 but must be read per-market, never hard-coded (P1-4).
- **Gamma `/markets`** — rich metadata incl. `conditionId, clobTokenIds (JSON
  string), outcomes, outcomePrices, closed, liquidityNum, volumeNum, spread,
  bestBid/bestAsk, endDate, umaResolutionStatuses, resolvedBy, negRisk, feesEnabled`.
  → *Impact:* resolution + liquidity + category are derivable here.
- **Data `/leaderboard`** — **404** on `data-api`. → *Impact:* pool-discovery path
  is wrong (P1-3); must re-verify or use holders/on-chain.

## B. Polymarket API / platform facts

- **CLOB V2** live **2026-04-28**; V1 SDKs and V1-signed orders no longer work.
  Source: parlay.run "Polymarket API: The Complete Developer Guide (2026, CLOB V2)",
  https://www.parlay.run/polymarket-api (checked 2026-07-24).
  *Impact:* any future live signing must target V2.
- **Rate limits** (Cloudflare, per 10s): Data `/trades` 200, `/positions` 150;
  CLOB `/book` 1500; Gamma `/markets` 300. Same source.
  *Impact:* 90s polling is comfortably inside limits (see API-cost note in ROADMAP).
- **Infra region** AWS **eu-west-2 (London)**. Source: newyorkcityservers.com
  latency guide (checked 2026-07-24). *Impact:* latency budget for any live path.
- **US regulatory status:** international Polymarket has been **geoblocked for US
  IPs since the 2022 CFTC settlement**, with a geoblock check before each order.
  A separate **Polymarket US** (CFTC-registered DCM, operator QCX LLC) launched
  **2025-12-03**, invite-only, broader access expected Q3–Q4 2026. Sources:
  tech-insider.org "Is Polymarket Legal in the USA? CFTC + 2026 Status";
  quantvps.com US-API note (checked 2026-07-24).
  *Impact:* the ONLY lawful US live path is Polymarket US when available — **not**
  VPN onto the international exchange. Confirms the mandate's VPN ban.

## C. Academic / empirical findings

- **Concentration of skill & poor out-of-sample persistence (KEY).**
  Gómez-Cram, Guo, Jensen & Kung (London Business School / Yale), **working paper
  (not peer-reviewed)**, released week of **2026-04-26**. SSRN abstract 6617059:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6617059 (via CoinDesk,
  https://www.coindesk.com/markets/2026/04/26/only-3-of-traders-drive-prediction-markets-accuracy-not-the-crowd-study-finds,
  checked 2026-07-24). Sample: 1.72M accounts, $13.76B, 2023–2025.
  - ~**3%** of traders drive most price discovery.
  - Only **12%** of top profit-earners beat a randomized-direction benchmark.
  - **~60% of "lucky winners" became losers** on separate event samples.
  *Impact:* **directly challenges the core premise.** Identifying persistently
  skilled, copyable traders is hard; most apparent skill is luck that reverses
  out-of-sample. This is why the audit mandates event-clustered, out-of-sample
  evidence and why micro-live is NO-GO without it.
- **Calibration.** Across ~28,407 resolved markets (Jan 2024 – May 2026),
  Polymarket prices were well-calibrated (mean abs. calibration error ~**2.1pp**).
  Sources: predscope.com / weex.com research round-ups (checked 2026-07-24).
  *Impact:* a well-calibrated price already embeds informed flow → the residual
  edge available to a late copier is small. Consistent with our synthetic result
  that the edge lives in *price inefficiency*, and that efficient markets leave ~0.
- **Spread vs accuracy.** Wider-spread (thinner, niche) markets show *lower*
  forecast error — informed specialists concentrate there. Same round-ups.
  *Impact:* a naive liquidity/tight-spread filter may exclude exactly the markets
  where specialist edge exists — a real design tension to test, not assume.

## D. Net research conclusion

Public data is free and rich enough for honest paper research. But the strongest
current evidence (well-calibrated prices; ~60% of top winners flip to losers
out-of-sample) says the **prior for a profitable late-copy edge is low**. Nothing
here proves the strategy works or fails on real data — it sets the bar for what
real evidence must clear (see `EXPERIMENTS.md`, `ROADMAP.md`).
