"""Tests for the SQLite store: raw persistence, dedup, restart safety."""

from src.store.db import Store

RAW = {
    "proxyWallet": "0xA",
    "conditionId": "m1",
    "outcome": "Yes",
    "side": "BUY",
    "price": 0.5,
    "size": 300,
    "timestamp": 1767225600,
}


def test_insert_and_read_raw_trade():
    with Store() as store:
        assert store.insert_raw_trade(RAW, source="data", wallet="0xA", market_id="m1")
        rows = list(store.iter_raw_trades(wallet="0xA"))
        assert rows == [RAW]


def test_duplicate_raw_trade_is_ignored():
    with Store() as store:
        assert store.insert_raw_trade(RAW, source="data") is True
        assert store.insert_raw_trade(RAW, source="data") is False
        assert store.count_raw_trades() == 1


def test_state_survives_restart(tmp_path):
    db_path = tmp_path / "state.db"
    store = Store(db_path)
    store.set_state("virtual_balance", "1000")
    store.set_state("last_cursor", "abc123")
    store.insert_raw_trade(RAW, source="data", wallet="0xA", market_id="m1")
    store.close()

    reopened = Store(db_path)
    assert reopened.get_state("virtual_balance") == "1000"
    assert reopened.get_state("last_cursor") == "abc123"
    assert reopened.count_raw_trades() == 1
    reopened.close()


def test_state_upsert_overwrites():
    with Store() as store:
        store.set_state("k", "v1")
        store.set_state("k", "v2")
        assert store.get_state("k") == "v2"
        assert store.get_state("missing", "default") == "default"
