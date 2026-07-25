"""Thin HTTP transport for the Polymarket REST APIs.

A ``GetJson`` is any callable ``(path, params) -> parsed JSON``. Production uses
:func:`httpx_get_json`; tests inject a fake that returns canned dicts, so no
network is required to exercise the client logic.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

GetJson = Callable[[str, Mapping[str, Any] | None], Any]

# Verified base URLs (Polymarket, 2026 / CLOB V2).
GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"


def httpx_get_json(base_url: str, *, timeout: float = 10.0) -> GetJson:
    """Build a live ``GetJson`` bound to ``base_url`` using httpx.

    Imported lazily so that importing the client module never requires httpx or
    a network stack in test/CI environments.
    """
    import httpx

    client = httpx.Client(base_url=base_url, timeout=timeout)

    def get(path: str, params: Mapping[str, Any] | None = None) -> Any:
        response = client.get(path, params=dict(params) if params else None)
        response.raise_for_status()
        return response.json()

    return get


def _clean(params: Mapping[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None so we don't send empty query params."""
    return {k: v for k, v in params.items() if v is not None}
