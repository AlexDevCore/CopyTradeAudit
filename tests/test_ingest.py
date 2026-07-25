"""Tests for ingest clients (offline, injected transport) and parsers."""

from datetime import timezone
from decimal import Decimal

import pytest
from src.ingest.polymarket import (
    ClobClient,
    DataClient,
    parse_orderbook,
    parse_trade,
)


class FakeTransport:
    """Records the last (path, params) and returns a canned payload."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, path, params=None):
        self.calls.append((path, dict(params) if params else None))
        return self.payload


def test_data_client_trades_cleans_none_and_sets_taker_flag():
    fake = FakeTransport([])
    client = DataClient(fake)
    client.trades(user="0xA", taker_only=True)
    path, params = fake.calls[-1]
    assert path == "/trades"
    assert params == {"user": "0xA", "takerOnly": "true"}  # market/before/limit dropped


def test_clob_client_fee_rate_path():
    fake = FakeTransport({"feeRateBps": 0})
    ClobClient(fake).fee_rate("tok-1")
    assert fake.calls[-1] == ("/fee-rate", {"token_id": "tok-1"})


def test_parse_trade_buy_yes():
    raw = {
        "proxyWallet": "0xA",
        "conditionId": "m1",
        "outcome": "Yes",
        "side": "BUY",
        "price": 0.52,
        "size": 100,
        "timestamp": 1767225600,
    }
    trade = parse_trade(raw)
    assert trade.wallet == "0xA"
    assert trade.market_id == "m1"
    assert trade.yes_delta == Decimal(100)  # buying YES -> +exposure
    assert trade.yes_price == Decimal("0.52")
    assert trade.timestamp.tzinfo == timezone.utc


def test_parse_trade_buy_no_is_negative_yes_equivalent():
    raw = {
        "proxyWallet": "0xB",
        "conditionId": "m1",
        "outcome": "No",
        "side": "BUY",
        "price": 0.40,
        "size": 100,
        "timestamp": 1767225600,
    }
    trade = parse_trade(raw)
    assert trade.yes_delta == Decimal(-100)  # buying NO -> -exposure
    assert trade.yes_price == Decimal("0.60")  # NO@0.40 == YES@0.60


def test_parse_trade_missing_field_raises():
    with pytest.raises(ValueError):
        parse_trade({"proxyWallet": "0xA"})


def test_parse_orderbook_sorts_levels():
    raw = {
        "asks": [{"price": 0.60, "size": 100}, {"price": 0.50, "size": 100}],
        "bids": [{"price": 0.45, "size": 100}, {"price": 0.48, "size": 100}],
        "timestamp": 1767225600,
    }
    book = parse_orderbook(raw, market_id="m1")
    assert [level.price for level in book.asks] == [Decimal("0.50"), Decimal("0.60")]
    assert [level.price for level in book.bids] == [Decimal("0.48"), Decimal("0.45")]
    assert book.best_ask == Decimal("0.50")
    assert book.best_bid == Decimal("0.48")
