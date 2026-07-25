"""SQLite store.

Two jobs in Phase B:
  1. Persist raw incoming payloads *verbatim* (before any normalisation), so
     every downstream calculation can be replayed and audited.
  2. Persist small app state (cursors, virtual balance) so a restart never
     loses progress.

Uses stdlib ``sqlite3`` only — no extra dependency.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    wallet      TEXT,
    market_id   TEXT,
    raw_json    TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    UNIQUE(source, raw_json)
);

CREATE TABLE IF NOT EXISTS raw_orderbooks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id   TEXT,
    token_id    TEXT,
    raw_json    TEXT NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    at           TEXT NOT NULL,
    kind         TEXT NOT NULL,
    market_id    TEXT,
    message      TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_raw_trades_wallet_market
    ON raw_trades (wallet, market_id);
"""


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class Store:
    """Thin repository over a SQLite database file (or ``:memory:``)."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- raw trades ---------------------------------------------------------

    def insert_raw_trade(
        self,
        raw: dict[str, Any],
        *,
        source: str,
        wallet: str | None = None,
        market_id: str | None = None,
    ) -> bool:
        """Persist one raw trade. Returns False if it was a duplicate."""
        payload = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        try:
            self._conn.execute(
                "INSERT INTO raw_trades (source, wallet, market_id, raw_json, ingested_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (source, wallet, market_id, payload, _now_iso()),
            )
        except sqlite3.IntegrityError:
            return False
        self._conn.commit()
        return True

    def iter_raw_trades(
        self, *, wallet: str | None = None, market_id: str | None = None
    ) -> Iterator[dict[str, Any]]:
        query = "SELECT raw_json FROM raw_trades"
        clauses: list[str] = []
        args: list[Any] = []
        if wallet is not None:
            clauses.append("wallet = ?")
            args.append(wallet)
        if market_id is not None:
            clauses.append("market_id = ?")
            args.append(market_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id"
        for row in self._conn.execute(query, args):
            yield json.loads(row["raw_json"])

    def count_raw_trades(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM raw_trades").fetchone()[0])

    def insert_raw_orderbook(
        self, raw: dict[str, Any], *, market_id: str, token_id: str
    ) -> None:
        payload = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO raw_orderbooks (market_id, token_id, raw_json, captured_at)"
            " VALUES (?, ?, ?, ?)",
            (market_id, token_id, payload, _now_iso()),
        )
        self._conn.commit()

    # --- app state ----------------------------------------------------------

    def set_state(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_state(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM app_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    # --- audit --------------------------------------------------------------

    def insert_audit_event(self, event: Any) -> None:
        """Persist one audit event (anything with a ``to_row()`` 5-tuple)."""
        at, kind, market_id, message, payload_json = event.to_row()
        self._conn.execute(
            "INSERT INTO audit_events (at, kind, market_id, message, payload_json)"
            " VALUES (?, ?, ?, ?, ?)",
            (at, kind, market_id, message, payload_json),
        )
        self._conn.commit()

    def iter_audit_events(self) -> Iterator[dict[str, Any]]:
        for row in self._conn.execute(
            "SELECT at, kind, market_id, message, payload_json FROM audit_events ORDER BY id"
        ):
            yield dict(row)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
