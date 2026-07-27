"""Can a free public weather model beat Polymarket temperature prices?

This tests a *forecasting* edge rather than a *copying* edge: instead of watching
other traders, we ask whether a publicly available numerical weather forecast,
as it stood BEFORE the event, priced the outcome better than the market did.

Leakage control is the whole game here:
  * Forecasts come from Open-Meteo's previous-runs archive
    (`temperature_2m_previous_day1` = the run issued a day earlier). Using today's
    analysis for a past date would be pure hindsight.
  * The market price used is the last trade at/before the same cutoff.
  * Forecast error sigma is estimated from OTHER days than the one being priced.

Network module — run explicitly, results cached to disk.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import time
from typing import Any

import httpx

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"
PREV_RUNS = "https://previous-runs-api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

_C = httpx.Client(timeout=40.0)

# Cities that appear in Polymarket's daily temperature markets.
CITIES: dict[str, tuple[float, float, str]] = {
    "london": (51.51, -0.13, "Europe/London"),
    "paris": (48.86, 2.35, "Europe/Paris"),
    "moscow": (55.76, 37.62, "Europe/Moscow"),
    "munich": (48.14, 11.58, "Europe/Berlin"),
    "berlin": (52.52, 13.40, "Europe/Berlin"),
    "madrid": (40.42, -3.70, "Europe/Madrid"),
    "rome": (41.90, 12.50, "Europe/Rome"),
    "shanghai": (31.23, 121.47, "Asia/Shanghai"),
    "guangzhou": (23.13, 113.26, "Asia/Shanghai"),
    "beijing": (39.90, 116.41, "Asia/Shanghai"),
    "hong kong": (22.32, 114.17, "Asia/Hong_Kong"),
    "tokyo": (35.68, 139.69, "Asia/Tokyo"),
    "seoul": (37.57, 126.98, "Asia/Seoul"),
    "singapore": (1.35, 103.82, "Asia/Singapore"),
    "new york": (40.71, -74.01, "America/New_York"),
    "nyc": (40.71, -74.01, "America/New_York"),
    "chicago": (41.88, -87.63, "America/Chicago"),
    "los angeles": (34.05, -118.24, "America/Los_Angeles"),
    "miami": (25.76, -80.19, "America/New_York"),
    "sydney": (-33.87, 151.21, "Australia/Sydney"),
    "delhi": (28.61, 77.21, "Asia/Kolkata"),
    "mumbai": (19.08, 72.88, "Asia/Kolkata"),
    "sao paulo": (-23.55, -46.63, "America/Sao_Paulo"),
    "buenos aires": (-34.60, -58.38, "America/Argentina/Buenos_Aires"),
    "mexico city": (19.43, -99.13, "America/Mexico_City"),
    "toronto": (43.65, -79.38, "America/Toronto"),
    "istanbul": (41.01, 28.98, "Europe/Istanbul"),
    "dubai": (25.20, 55.27, "Asia/Dubai"),
}


# Polymarket resolves each ladder against ONE named airport station via
# Wunderground (the URL's last path segment is its ICAO code) — not a city-centre
# grid point. Querying the city centre instead produces a systematic 1-2 °C
# mismatch against the resolution source, which silently invalidates the whole
# experiment. These are the station coordinates.
ICAO: dict[str, tuple[float, float, str]] = {
    "EGLC": (51.505, 0.055, "Europe/London"),  # London City
    "EGLL": (51.470, -0.454, "Europe/London"),  # Heathrow
    "LFPB": (48.969, 2.441, "Europe/Paris"),  # Paris-Le Bourget
    "LFPG": (49.010, 2.548, "Europe/Paris"),  # Charles de Gaulle
    "ZSPD": (31.143, 121.805, "Asia/Shanghai"),  # Shanghai Pudong
    "ZSSS": (31.198, 121.336, "Asia/Shanghai"),  # Shanghai Hongqiao
    "ZBAA": (40.080, 116.584, "Asia/Shanghai"),  # Beijing Capital
    "ZGGG": (23.392, 113.299, "Asia/Shanghai"),  # Guangzhou Baiyun
    "EDDM": (48.353, 11.786, "Europe/Berlin"),  # Munich
    "EDDB": (52.362, 13.500, "Europe/Berlin"),  # Berlin Brandenburg
    "RKSI": (37.469, 126.451, "Asia/Seoul"),  # Incheon
    "RKSS": (37.558, 126.791, "Asia/Seoul"),  # Gimpo
    "LEMD": (40.472, -3.561, "Europe/Madrid"),  # Madrid Barajas
    "LTFM": (41.262, 28.742, "Europe/Istanbul"),  # Istanbul
    "LTBA": (40.977, 28.821, "Europe/Istanbul"),  # Istanbul Ataturk
    "RJTT": (35.553, 139.781, "Asia/Tokyo"),  # Tokyo Haneda
    "RJAA": (35.765, 140.386, "Asia/Tokyo"),  # Narita
    "WSSS": (1.359, 103.989, "Asia/Singapore"),  # Changi
    "KNYC": (40.779, -73.969, "America/New_York"),  # NYC Central Park
    "KLGA": (40.777, -73.873, "America/New_York"),  # LaGuardia
    "KORD": (41.979, -87.904, "America/Chicago"),  # O'Hare
    "KLAX": (33.942, -118.408, "America/Los_Angeles"),
    "KMIA": (25.796, -80.287, "America/New_York"),
    "LIRF": (41.800, 12.239, "Europe/Rome"),  # Rome Fiumicino
    "UUEE": (55.973, 37.415, "Europe/Moscow"),  # Sheremetyevo
    "OMDB": (25.253, 55.365, "Asia/Dubai"),  # Dubai
    "VIDP": (28.556, 77.100, "Asia/Kolkata"),  # Delhi
    "SBGR": (-23.435, -46.473, "America/Sao_Paulo"),  # Sao Paulo Guarulhos
    "SAEZ": (-34.822, -58.536, "America/Argentina/Buenos_Aires"),
    "YSSY": (-33.946, 151.177, "Australia/Sydney"),
    "CYYZ": (43.677, -79.631, "America/Toronto"),
    "MMMX": (19.436, -99.072, "America/Mexico_City"),
}

_ICAO_RE = re.compile(r"/([A-Z]{4})/?\s*$")


def station_of(resolution_source: str | None) -> tuple[str, float, float, str] | None:
    """Extract the ICAO station from a market's resolutionSource URL."""
    if not resolution_source:
        return None
    m = _ICAO_RE.search(resolution_source.strip())
    if not m:
        return None
    code = m.group(1).upper()
    hit = ICAO.get(code)
    return (code, *hit) if hit else None


def _get(url: str, **params: Any) -> Any:
    for attempt in range(4):
        r = _C.get(url, params=params)
        if r.status_code == 429:
            time.sleep(1 + attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def _city_of(title: str) -> tuple[str, tuple[float, float, str]] | None:
    low = title.lower()
    for name, coords in CITIES.items():
        if name in low:
            return name, coords
    return None


_BUCKET_BELOW = re.compile(r"(-?\d+)\s*°?\s*c?\s*or\s*below", re.IGNORECASE)
_BUCKET_ABOVE = re.compile(r"(-?\d+)\s*°?\s*c?\s*or\s*(above|higher)", re.IGNORECASE)
_BUCKET_EXACT = re.compile(r"^\s*(-?\d+)\s*°?\s*c?\s*$", re.IGNORECASE)


def parse_bucket(label: str) -> tuple[str, int] | None:
    """'24°C or below' -> ('below', 24); '25°C' -> ('exact', 25)."""
    if not label:
        return None
    m = _BUCKET_BELOW.search(label)
    if m:
        return "below", int(m.group(1))
    m = _BUCKET_ABOVE.search(label)
    if m:
        return "above", int(m.group(1))
    m = _BUCKET_EXACT.match(label.strip())
    if m:
        return "exact", int(m.group(1))
    return None


def bucket_probability(kind: str, value: int, mu: float, sigma: float) -> float:
    """P(rounded daily max falls in this bucket) under Normal(mu, sigma).

    Polymarket resolves on the rounded integer high, so 'exact 25' means the true
    max lands in [24.5, 25.5).
    """

    def cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))

    if kind == "below":
        return cdf(value + 0.5)
    if kind == "above":
        return 1.0 - cdf(value - 0.5)
    return cdf(value + 0.5) - cdf(value - 0.5)


def forecast_and_actual(
    lat: float, lon: float, tz: str, day: str, *, lead_days: int = 1
) -> tuple[float | None, float | None]:
    """(day-`lead_days` forecast max, actual max) in °C for `day` (YYYY-MM-DD)."""
    var = f"temperature_2m_previous_day{lead_days}"
    fc = None
    try:
        d = _get(
            PREV_RUNS,
            latitude=lat,
            longitude=lon,
            start_date=day,
            end_date=day,
            hourly=var,
            timezone=tz,
        ).get("hourly", {})
        vals = [v for v in d.get(var, []) if v is not None]
        fc = max(vals) if vals else None
    except Exception:
        pass
    act = None
    try:
        d = _get(
            ARCHIVE,
            latitude=lat,
            longitude=lon,
            start_date=day,
            end_date=day,
            daily="temperature_2m_max",
            timezone=tz,
        ).get("daily", {})
        vals = [v for v in d.get("temperature_2m_max", []) if v is not None]
        act = vals[0] if vals else None
    except Exception:
        pass
    return fc, act


def collect_events(limit_per_type: int = 200) -> list[dict]:
    """Closed daily-temperature events with parsed city, date and buckets."""
    out: list[dict] = []
    seen: set[str] = set()
    for q in ("highest temperature", "temperature in"):
        res = _get(f"{GAMMA}/public-search", q=q, limit_per_type=limit_per_type)
        for ev in res.get("events") or []:
            if not ev.get("closed") or ev.get("id") in seen:
                continue
            title = ev.get("title") or ""
            city = _city_of(title)
            if city is None:
                continue
            end = ev.get("endDate")
            if not end:
                continue
            day = end[:10]
            # Prefer the exact station this event resolves against; fall back to
            # the city centre only if the ICAO code is unknown (and flag it).
            first = (ev.get("markets") or [{}])[0]
            st = station_of(first.get("resolutionSource"))
            buckets = []
            for m in ev.get("markets") or []:
                b = parse_bucket(m.get("groupItemTitle") or m.get("question") or "")
                if b is None:
                    continue
                prices = m.get("outcomePrices")
                if isinstance(prices, str):
                    prices = json.loads(prices)
                if not prices or len(prices) != 2:
                    continue
                won = float(prices[0]) >= 0.99
                buckets.append(
                    {
                        "market_id": m.get("conditionId"),
                        "kind": b[0],
                        "value": b[1],
                        "won": won,
                        "label": m.get("groupItemTitle"),
                    }
                )
            if len(buckets) < 3 or not any(b["won"] for b in buckets):
                continue
            seen.add(ev.get("id"))
            out.append(
                {
                    "event_id": str(ev.get("id")),
                    "title": title,
                    "city": city[0],
                    "station": st[0] if st else None,
                    "lat": st[1] if st else city[1][0],
                    "lon": st[2] if st else city[1][1],
                    "tz": st[3] if st else city[1][2],
                    "day": day,
                    "end": end,
                    "buckets": buckets,
                }
            )
    return out


def market_price_before(
    market_id: str, cutoff_ts: int, *, max_pages: int = 8
) -> float | None:
    """Last traded YES price at or before `cutoff_ts` for a bucket market.

    Must page backwards. The busiest buckets — the ones nearest the forecast, and
    the ones that actually win — have many pages of trades AFTER the cutoff.
    Reading only the newest page returns None for exactly those markets, leaving
    a sample of illiquid tail buckets and biasing any result built on it beyond
    repair. (This bug produced a spurious 0-for-18 result before it was caught.)
    """
    before: str | None = None
    for _ in range(max_pages):
        params: dict[str, Any] = {"market": market_id, "limit": 500}
        if before:
            params["before"] = before
        try:
            rows = _get(f"{DATA}/trades", **params)
        except Exception:
            return None
        if not rows:
            return None
        best: tuple[int, float] | None = None
        oldest: int | None = None
        for x in rows:
            ts = int(x.get("timestamp", 0))
            oldest = ts if oldest is None else min(oldest, ts)
            if ts > cutoff_ts:
                continue
            price = float(x.get("price", 0))
            yes = (
                price
                if str(x.get("outcome", "")).lower().startswith("y")
                else 1.0 - price
            )
            if best is None or ts > best[0]:
                best = (ts, yes)
        if best is not None:
            return best[1]
        if oldest is None or len(rows) < 500:
            return None
        before = str(oldest)  # page further back in time
        time.sleep(0.03)
    return None


def estimate_sigma(events: list[dict], *, lead_days: int = 1) -> tuple[float, int]:
    """Empirical std of (actual − forecast) daily max, across the sample."""
    errs: list[float] = []
    for ev in events:
        fc, act = forecast_and_actual(
            ev["lat"], ev["lon"], ev["tz"], ev["day"], lead_days=lead_days
        )
        ev["forecast"] = fc
        ev["actual"] = act
        if fc is not None and act is not None:
            errs.append(act - fc)
        time.sleep(0.05)
    if len(errs) < 3:
        return (1.5, len(errs))
    return (statistics.pstdev(errs) or 1.0, len(errs))
