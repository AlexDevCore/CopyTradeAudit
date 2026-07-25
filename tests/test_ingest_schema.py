"""Parser tests pinned to the LIVE Polymarket schema (validated 2026-07).

These use real payload shapes captured from the public read-only APIs so the
parsers cannot silently drift from what the endpoints actually return.
"""

from datetime import timezone
from decimal import Decimal

from src.ingest.polymarket import parse_orderbook, parse_trade

# Real /trades row shape (Data API).
LIVE_TRADE = {
    "proxyWallet": "0xe84f8e41ad5ad780e24f7bcbdca23b5f615ab777",
    "side": "BUY",
    "asset": "58177365395763611745860379787172653718070215320088612486671609827141288513094",
    "conditionId": "0x39fd7fda153d1121441a03bc64ed461b2ae7ccf1cb887ba4f96356cabf8fca0a",
    "size": 9.75,
    "price": 0.36,
    "timestamp": 1784943456,  # seconds (10 digits)
    "outcome": "No",
    "outcomeIndex": 999,  # unreliable sentinel — we rely on `outcome` string
    "transactionHash": "0x1052e69a…",
}

# Real /book shape (CLOB): asks DESCENDING, timestamp in MILLISECONDS.
LIVE_BOOK = {
    "market": "0x7d0aaf81…",
    "asset_id": "27146956…",
    "timestamp": "1784943842216",  # milliseconds (13 digits)
    "bids": [{"price": "0.34", "size": "500"}, {"price": "0.35", "size": "100"}],
    "asks": [{"price": "0.40", "size": "200"}, {"price": "0.37", "size": "50"}],
}


def test_live_trade_parses_to_no_direction_seconds_ts():
    tr = parse_trade(LIVE_TRADE)
    assert tr.wallet == LIVE_TRADE["proxyWallet"]
    assert tr.market_id == LIVE_TRADE["conditionId"]
    assert tr.yes_delta == Decimal("-9.75")  # BUY No -> negative YES exposure
    assert tr.yes_price == Decimal("0.64")  # No@0.36 == Yes@0.64
    # seconds timestamp -> a 2026 date, not year ~58000
    assert tr.timestamp.year == 2026
    assert tr.timestamp.tzinfo == timezone.utc


def test_live_trade_has_no_maker_taker_flag():
    # The public /trades payload carries no maker/taker info -> must stay unknown.
    tr = parse_trade(LIVE_TRADE)
    assert tr.is_taker is None


def test_live_book_millisecond_timestamp_and_best_prices():
    book = parse_orderbook(LIVE_BOOK, market_id="m")
    # ms timestamp normalised to 2026, not the far future
    assert book.timestamp.year == 2026
    # asks re-sorted ascending -> best ask is the lowest, regardless of API order
    assert book.best_ask == Decimal("0.37")
    assert book.best_bid == Decimal("0.35")
