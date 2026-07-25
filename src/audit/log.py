"""Append-only audit log.

Records the chronological story required by the spec: data received, signals,
accepted/rejected decisions, errors, halts, strategy-version changes. Optionally
persisted through the store so it survives restarts. Deterministic: the caller
supplies the timestamp, so replays reproduce the log exactly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class AuditKind(str, Enum):
    DATA = "DATA"
    SIGNAL = "SIGNAL"
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REJECTED = "REJECTED"
    RESOLUTION = "RESOLUTION"
    ERROR = "ERROR"
    HALT = "HALT"
    STRATEGY_VERSION = "STRATEGY_VERSION"


@dataclass(frozen=True)
class AuditEvent:
    at: datetime
    kind: AuditKind
    market_id: str | None
    message: str
    payload: dict[str, Any]

    def to_row(self) -> tuple[str, str, str | None, str, str]:
        return (
            self.at.isoformat(),
            self.kind.value,
            self.market_id,
            self.message,
            json.dumps(self.payload, sort_keys=True, separators=(",", ":")),
        )


class AuditLog:
    """In-memory log with optional write-through to a store."""

    def __init__(self, store: Any | None = None) -> None:
        self._events: list[AuditEvent] = []
        self._store = store

    def record(
        self,
        at: datetime,
        kind: AuditKind,
        message: str,
        *,
        market_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(at, kind, market_id, message, payload or {})
        self._events.append(event)
        if self._store is not None:
            self._store.insert_audit_event(event)
        return event

    @property
    def events(self) -> list[AuditEvent]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)
