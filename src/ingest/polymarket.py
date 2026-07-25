"""Polymarket API clients + parsers (Gamma / Data / CLOB).

Endpoints and bases verified against the 2026 (CLOB V2) API. Trade/order-book
field names below are the documented public shapes; they MUST be re-validated
against a live sample before the ingest output is trusted (tracked in DESIGN.md
open questions). Parsers are defensive and keep the raw payload untouched so the
store can persist it verbatim.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.domain.models import Action, Level, Orderbook, Side, TraderTrade
from src.ingest.http import GetJson, _clean


class GammaClient:
    """Markets, events, tags, resolution metadata."""

    def __init__(self, get_json: GetJson) -> None:
        self._get = get_json

    def markets(
        self,
        *,
        tag_id: int | None = None,
        closed: bool | None = None,
        liquidity_num_min: float | None = None,
        limit: int | None = None,
        after_cursor: str | None = None,
    ) -> Any:
        params = _clean(
            {
                "tag_id": tag_id,
                "closed": closed,
                "liquidity_num_min": liquidity_num_min,
                "limit": limit,
                "after_cursor": after_cursor,
            }
        )
        return self._get("/markets/keyset", params)

    def market_by_slug(self, slug: str) -> Any:
        return self._get(f"/markets/slug/{slug}", None)

    def tags(self) -> Any:
        return self._get("/tags", None)


class DataClient:
    """Public trades, positions, holders, leaderboard."""

    def __init__(self, get_json: GetJson) -> None:
        self._get = get_json

    def trades(
        self,
        *,
        user: str | None = None,
        market: str | None = None,
        before: str | None = None,
        limit: int | None = None,
        taker_only: bool | None = None,
    ) -> Any:
        # NOTE: the public /trades endpoint may default to taker-only results.
        # We pass the flag explicitly and never assume the default is complete.
        params = _clean(
            {
                "user": user,
                "market": market,
                "before": before,
                "limit": limit,
                "takerOnly": None if taker_only is None else str(taker_only).lower(),
            }
        )
        return self._get("/trades", params)

    def leaderboard(self, **params: Any) -> Any:
        return self._get("/leaderboard", _clean(params))

    def holders(self, market: str) -> Any:
        return self._get("/holders", {"market": market})

    def positions(self, user: str) -> Any:
        return self._get("/positions", {"user": user})


class ClobClient:
    """Order books, prices, per-market fee rate."""

    def __init__(self, get_json: GetJson) -> None:
        self._get = get_json

    def book(self, token_id: str) -> Any:
        return self._get("/book", {"token_id": token_id})

    def fee_rate(self, token_id: str) -> Any:
        # Fees are protocol-set per market — always fetched, never hard-coded.
        return self._get("/fee-rate", {"token_id": token_id})

    def price(self, token_id: str, side: str) -> Any:
        return self._get("/price", {"token_id": token_id, "side": side})

    def midpoint(self, token_id: str) -> Any:
        return self._get("/midpoint", {"token_id": token_id})


# --------------------------------------------------------------------------- #
# Parsers: raw JSON -> domain models. Assumed public field shapes; validate
# against a live sample before trusting (see DESIGN.md open questions).
# --------------------------------------------------------------------------- #

# Field name candidates seen across Polymarket's public payloads.
_WALLET_KEYS = ("proxyWallet", "user", "maker", "wallet")
_MARKET_KEYS = ("conditionId", "market", "condition_id", "marketId")
_PRICE_KEYS = ("price",)
_SIZE_KEYS = ("size", "shares", "amount")
_TS_KEYS = ("timestamp", "matchTime", "time")
_SIDE_KEYS = ("side",)
_OUTCOME_KEYS = ("outcome", "outcomeSide")


def _first(raw: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _to_side(value: Any) -> Side:
    text = str(value).strip().lower()
    if text in ("yes", "y", "1", "true"):
        return Side.YES
    if text in ("no", "n", "0", "false"):
        return Side.NO
    raise ValueError(f"cannot map outcome to Side: {value!r}")


def _to_action(value: Any) -> Action:
    text = str(value).strip().upper()
    if text in ("BUY", "B"):
        return Action.BUY
    if text in ("SELL", "S"):
        return Action.SELL
    raise ValueError(f"cannot map side to Action: {value!r}")


def _epoch_to_dt(value: float) -> datetime:
    """Convert a unix epoch to UTC, auto-detecting seconds vs milliseconds.

    Polymarket mixes units: Data /trades uses seconds (10 digits) while CLOB
    /book uses milliseconds (13 digits). A raw ms value fed to a seconds parser
    lands in the year ~58000, so we normalise by magnitude. Anything >= 1e12 is
    treated as milliseconds. (Validated against live payloads, 2026-07.)
    """
    v = float(value)
    if v >= 1e12:  # milliseconds
        v /= 1000.0
    return datetime.fromtimestamp(v, tz=timezone.utc)


def _to_dt(value: Any) -> datetime:
    # Accept unix seconds/millis (int/str) or ISO 8601.
    if isinstance(value, (int, float)):
        return _epoch_to_dt(value)
    text = str(value)
    if text.isdigit():
        return _epoch_to_dt(int(text))
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def parse_trade(raw: Mapping[str, Any]) -> TraderTrade:
    """Map one raw trade dict into a normalised :class:`TraderTrade`."""
    wallet = _first(raw, _WALLET_KEYS)
    market = _first(raw, _MARKET_KEYS)
    outcome = _first(raw, _OUTCOME_KEYS)
    side = _first(raw, _SIDE_KEYS)
    price = _first(raw, _PRICE_KEYS)
    size = _first(raw, _SIZE_KEYS)
    ts = _first(raw, _TS_KEYS)
    missing = [
        name
        for name, val in (
            ("wallet", wallet),
            ("market", market),
            ("outcome", outcome),
            ("side", side),
            ("price", price),
            ("size", size),
            ("timestamp", ts),
        )
        if val is None
    ]
    if missing:
        raise ValueError(f"trade missing fields {missing}: {dict(raw)!r}")

    taker = raw.get("takerOnly")
    is_taker = None if taker is None else bool(taker)

    return TraderTrade.from_token_trade(
        wallet=str(wallet),
        market_id=str(market),
        side=_to_side(outcome),
        action=_to_action(side),
        shares=Decimal(str(size)),
        price=Decimal(str(price)),
        timestamp=_to_dt(ts),
        is_taker=is_taker,
    )


def parse_orderbook(raw: Mapping[str, Any], *, market_id: str) -> Orderbook:
    """Map a raw CLOB ``/book`` payload into an :class:`Orderbook`.

    Asks are returned sorted ascending, bids descending, regardless of source
    ordering, so execution can always walk from the best price outward.
    """

    def levels(rows: Any) -> list[Level]:
        out: list[Level] = []
        for row in rows or ():
            price = row.get("price") if isinstance(row, Mapping) else row[0]
            size = row.get("size") if isinstance(row, Mapping) else row[1]
            out.append(Level(price=Decimal(str(price)), size=Decimal(str(size))))
        return out

    asks = sorted(levels(raw.get("asks")), key=lambda level: level.price)
    bids = sorted(levels(raw.get("bids")), key=lambda level: level.price, reverse=True)
    ts = _to_dt(_first(raw, _TS_KEYS) or 0)
    return Orderbook(
        market_id=market_id, timestamp=ts, asks=tuple(asks), bids=tuple(bids)
    )
