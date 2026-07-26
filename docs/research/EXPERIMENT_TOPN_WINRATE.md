# Experiment — "follow the top win-rate traders, bet bigger"

Tested exactly as proposed: take the **top 10–20 traders by win rate**, follow
the **majority direction**, **exit early when they exit**, and use **fixed dollar
stakes** (bigger on high win rate). Run on the committed real sports log
(`data/real_sports_90d.json.gz`), leakage-safe (top-N built only from markets
resolved **before** each signal).

Code: `src/backtest/variants.py` · reproduce: see bottom.

## Raw result — looks fantastic

| variant | trades | events | P&L | ROI | win rate |
|---|---|---|---|---|---|
| top10 by win rate, $5 | 17 | 3 | +$2.03 | +2.4% | **100%** |
| top10 by win rate, $25 | 17 | 3 | +$10.15 | +2.4% | **100%** |
| top20 by win rate, $25 | 36 | 5 | +$36.82 | +4.1% | **100%** |
| top20 by win rate, $50 | 36 | 5 | +$73.65 | +4.1% | **100%** |
| top20, rank by Wilson, $25 | 35 | 5 | +$34.05 | +3.9% | 100% |
| top20, rank by ROI, $25 | 10 | 2 | +$5.10 | +2.0% | 100% |

**36 trades, zero losses, profit scales with stake.** Now the diagnostics.

## Why it is a trap

### 1. Ranking by win rate *selects* favourite-buyers by construction

| Entry price | value |
|---|---|
| median | **0.980** |
| mean | 0.963 |
| above 0.90 | **32 / 36** |
| above 0.95 | **31 / 36** |

Sorting traders by win rate finds the people who buy near-certainties. Copying
them means buying at 98¢.

### 2. The payoff is brutally asymmetric

At the mean entry of 0.963:

- win → **+0.037**/share · loss → **−0.963**/share
- **one loss wipes out 26 wins**
- **breakeven win rate = 96.3%** — we observed 100%, on 5 events

At **$25/trade**: one win = **+$0.95**, one loss = **−$25.00**.
At **$50/trade**: one win = **+$1.91**, one loss = **−$50.00**.

Bigger stakes do not improve the odds; they only enlarge the downside. Betting
more *because* the win rate is high is backwards — the high win rate is the
*consequence* of a bad risk/reward, not evidence of skill.

### 3. One event away from disaster

The 36 trades sit on only **5 events**. Flipping a single event:

| if this event had lost | per-share total | ≈ P&L at $25/trade |
|---|---|---|
| (current, all won) | +1.324 | +$36.82 |
| event 213293 (9 trades) | −7.676 | ≈ −$212 |
| **event 315342 (22 trades)** | **−20.676** | **≈ −$537 (balance $1000 → $463)** |

One ordinary sporting upset turns +$37 into **−$537**, a **54% drawdown**. At
$50/trade that single event exceeds the entire $1000 balance.

### 4. The exit rule did nothing

`exit-when-they-exit` **fired on 0 of 36 trades** — identical P&L to holding. The
followed traders never cut before resolution, so the rule is untested here, not
validated. (Mechanically it also cannot help this shape: exiting a 0.98 position
saves at most ~2¢ while the risk is 98¢.)

### 5. No statistical evidence either way

5 events is below `MIN_EVENTS_FOR_CI = 8`; every variant reports
`CI [-inf, +inf] → no-edge`. The 100% win rate is not evidence — it is what a
96%-breakeven strategy looks like right before it isn't.

## Verdict

**REJECTED.** The variant is profitable in-sample only because no favourite lost
during a 5-event window. It requires a **96.3% hit rate just to break even**, and
the proposed "bet bigger on high win rate" rule maximises exposure exactly where
the loss asymmetry is worst. This is picking up pennies in front of a steamroller,
with stake size deciding how close you stand.

Ranking by **ROI** (the price-aware metric) instead of win rate produced fewer
trades and no edge either — but it did not build the 98¢ portfolio, which is the
behaviour we want to keep.

---

# Follow-up — ROI ranking + entry-price ceiling

The salvage attempt: keep the consensus idea, but rank traders by **ROI** (price
aware) instead of win rate, and **refuse entries above a price ceiling** where the
payoff math is hopeless.

## Result: refusing near-certainties leaves nothing to trade

| variant (top20, hold, $25) | trades | events | median entry | P&L | ROI |
|---|---|---|---|---|---|
| rank=ROI, no cap | 10 | 2 | 0.980 | +$5.10 | +2.0% |
| **rank=ROI, cap 0.90** | **0** | 0 | — | $0.00 | — |
| rank=ROI, cap 0.80 | 0 | 0 | — | $0.00 | — |
| rank=win rate, cap 0.90 | 4 | 2 | 0.856 | +$18.54 | +18.5% |
| rank=win rate, cap 0.80 | 1 | 1 | 0.777 | +$7.17 | +28.7% |

Widening the pool with the ceiling on turns the result **negative**:

| top-N (ROI, cap 0.90) | trades | events | P&L | ROI |
|---|---|---|---|---|
| top30 | 1 | 1 | −$25.00 | −100% |
| top50 | 3 | 2 | −$16.41 | −21.9% |
| top100 | 5 | 3 | −$6.46 | −5.2% |

## The decisive diagnostic: copying adds nothing over the price

Widest possible copy net (top200, no cap) = 37 trades. Bucketed by entry price,
next to what a **price-only** bet (no traders involved at all) earned in the same
band:

| entry band | copy: n | copy: mean PnL/share | price-only: n | price-only: mean PnL/share |
|---|---|---|---|---|
| 0.00–0.10 | 1 | −0.0240 | 40 | −0.0284 |
| 0.50–0.80 | 1 | +0.2228 | 4 | +0.1232 |
| 0.80–0.90 | 1 | +0.1887 | 3 | −0.1604 |
| 0.90–0.95 | 3 | **+0.0900** | 4 | **+0.0925** |
| **0.95–1.01** | **31** | **+0.0207** | **39** | **+0.0211** |

In the only bands with meaningful counts, **copying and blind price-based buying
are indistinguishable**: +0.0207 vs +0.0211 at 0.95+, +0.0900 vs +0.0925 at
0.90–0.95. The tracked traders contribute **zero information** — 84% of copy
trades land in the 0.95+ bucket and earn exactly what anyone buying that bucket
earned.

Also note: every 0.90+ favourite in this window won (39/39). In a normal window
~1–2 should lose; a single upset flips the band negative. The apparent profit is
the favourite premium collected during an upset-free 90 days, not an edge.

## Final verdict on this family

**REJECTED — and now explained.** The strategy's entire apparent profitability is
the price band, not the traders:

- Remove the near-certainty zone → **no trades at all** (ROI ranking) or a
  negative result (wider pools).
- Keep it → you are running a 96%-breakeven book where one upset erases 26 wins.
- Either way the traders add nothing measurable over reading the price.

This is the cleanest evidence so far that **late copying of public Polymarket
signals carries no edge** in this dataset, and it matches the literature
(well-calibrated prices; skill rarely persists out-of-sample).

## Reproduce

```bash
uv run python -m src.backtest.real          # baseline tables
# variants: src/backtest/variants.py -> TopNConfig(rank_by=…, max_entry_price=…)
```
