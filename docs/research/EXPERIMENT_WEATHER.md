# Experiment — can a free public weather model beat Polymarket?

A *forecasting* edge test rather than a *copying* one: instead of watching other
traders, ask whether a publicly available numerical forecast, as it stood before
the event, priced daily-temperature ladders better than the market.

Code: `src/backtest/weather.py`, `src/backtest/run_weather.py`

## Result: **INCONCLUSIVE — blocked on resolution-source fidelity**

The test does not currently produce a valid answer, and the numbers it does
produce must not be reported as evidence. Here is exactly why.

## Setup

- **Markets:** 11 resolved daily-temperature events (ladders of ~11 buckets:
  "24°C or below", "25°C", … "32°C or higher").
- **Forecast (leakage-safe):** Open-Meteo *previous-runs* archive,
  `temperature_2m_previous_day1` — the run issued a day earlier, i.e. what a
  bettor could actually have known. Using today's analysis for a past date would
  be hindsight.
- **Market price:** last trade at/before **06:00 local on the event day** — the
  forecast exists by then, the daily max (≈14–16h local) does not.
- **Probability model:** Normal(forecast, σ) integrated over each bucket, with σ
  estimated **leave-one-event-out**.

## Two bugs found and fixed along the way

1. **Pagination bias.** `market_price_before` read only the newest page of
   trades. The busiest buckets — the ones nearest the forecast, and the ones that
   actually win — have many pages *after* the cutoff, so they returned `None`.
   The sample silently reduced to illiquid tail buckets. Fixed by paging backwards.
2. **Wrong cutoff.** These ladders only open ~12h before resolution, so the
   original "end − 24h" cutoff predated all trading. Moved to 06:00 local.

## The blocker: the resolution source is a station, not a grid

Each market resolves against **one named airport station via Wunderground** —
the ICAO code is the last path segment of `resolutionSource`:

| event | station |
|---|---|
| London | `EGLC` London City Airport |
| Shanghai | `ZSPD` Pudong International |
| Paris | `LFPB` Paris-Le Bourget |

Querying the city centre instead of the station was a real error, and fixing it
measurably improved the forecast (error sd **1.59 → 1.26 °C**, bias +0.09 → −0.09).

But it did not fix the underlying mismatch:

> **My reconstructed "actual" rounds to the winning bucket in only 1 of 11 events.**

| city | station | my actual (rounded) | winning bucket |
|---|---|---|---|
| London | EGLC | 26 | **27** |
| Paris | LFPB | 25 | **26** |
| Munich | EDDM | 26 | **27** |
| Tokyo | RJTT | 31 | **32** |
| Singapore | WSSS | 29 | **30** |
| Guangzhou | ZGGG | 28 | **29** |
| Madrid | LEMD | 31 | 31 ✔ |
| Beijing | ZBAA | 31 | **34** |
| Seoul | RKSI | 28 | **31** |

A consistent **+1 °C** offset (occasionally +2/+3). Cause: Wunderground reports
the station's **observed** maximum (METAR peak), while Open-Meteo's archive is a
**gridded reanalysis**, which is known to smooth and understate daily maxima.

So the probability model is centred roughly 1 °C below the scale the market
actually settles on. It therefore buys buckets that are systematically too cold
and loses every time — **0 wins in 18 trades**. That number measures a data
mismatch, not a forecasting edge, and is reported here only to be dismissed.

## What a valid version needs

1. **Station observations, not reanalysis** — a METAR/Wunderground-equivalent
   archive for the exact ICAO stations, matching what resolution reads.
2. **A bias-corrected model** — if only gridded data is available, the
   grid→station offset must be calibrated out-of-sample, not fitted on the same
   events being priced.
3. **A far bigger sample.** 11 events is underpowered no matter how clean the
   data. These ladders run daily per city, so forward collection accumulates
   quickly.

## Separately: capacity makes this uninvestable anyway

Measured earlier on live temperature books: **$12 total across the top five ask
levels**, median trade **$5.99**, 96% of trades under $100. Even a genuine edge
here supports tens of dollars, not a business. This remains a knowledge question,
not an income path.

## Honest status

`INCONCLUSIVE`. The hypothesis — that a public model can out-forecast these
markets — is **untested**, not disproven. What is established: the naive version
of the test is invalid, and the precise reason is known.
