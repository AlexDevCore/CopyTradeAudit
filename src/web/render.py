"""Tiny server-side HTML rendering. No template engine, no external assets.

Everything user-visible goes through html.escape. Values shown are our own
paper-mode numbers, but escaping keeps audit/reason text safe regardless.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from html import escape
from typing import Any

_NAV = [
    ("/", "Dashboard"),
    ("/markets", "Markets"),
    ("/traders", "Traders"),
    ("/portfolio", "Paper portfolio"),
    ("/audit", "Audit log"),
]

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 system-ui, sans-serif; }
header { display: flex; align-items: center; gap: 16px; padding: 12px 20px;
         border-bottom: 1px solid #8884; position: sticky; top: 0;
         background: Canvas; }
nav a { margin-right: 14px; text-decoration: none; color: inherit; opacity: .7; }
nav a.active { opacity: 1; font-weight: 600; border-bottom: 2px solid currentColor; }
.badge { margin-left: auto; padding: 3px 10px; border-radius: 999px;
         font-weight: 700; font-size: 12px; letter-spacing: .5px; }
.badge.PAPER { background: #2e7d3222; color: #2e7d32; border: 1px solid #2e7d3288; }
.badge.LIVE  { background: #c6282822; color: #c62828; border: 1px solid #c6282888; }
main { padding: 20px; max-width: 1100px; }
h1 { font-size: 18px; margin: 0 0 16px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px,1fr));
         gap: 12px; margin-bottom: 24px; }
.card { border: 1px solid #8884; border-radius: 8px; padding: 12px 14px; }
.card .k { opacity: .6; font-size: 12px; }
.card .v { font-size: 20px; font-weight: 600; margin-top: 2px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid #8883;
         white-space: nowrap; }
th { opacity: .6; font-weight: 600; font-size: 12px; text-transform: uppercase; }
.pos { color: #2e7d32; } .neg { color: #c62828; }
.muted { opacity: .55; }
.empty { opacity: .55; padding: 20px 0; }
"""


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def layout(title: str, active_path: str, body: str, *, mode: str = "PAPER") -> str:
    nav = "".join(
        f'<a href="{href}" class="{"active" if href == active_path else ""}">{escape(label)}</a>'
        for href, label in _NAV
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>CopyTrader · {escape(title)}</title><style>{_CSS}</style></head><body>"
        f"<header><strong>CopyTrader</strong><nav>{nav}</nav>"
        f"<span class='badge {escape(mode)}'>{escape(mode)}</span></header>"
        f"<main><h1>{escape(title)}</h1>{body}</main></body></html>"
    )


def cards(pairs: Sequence[tuple[str, Any]]) -> str:
    items = "".join(
        f"<div class='card'><div class='k'>{escape(k)}</div>"
        f"<div class='v'>{escape(_fmt(v))}</div></div>"
        for k, v in pairs
    )
    return f"<div class='cards'>{items}</div>"


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        return "<p class='empty'>No data yet.</p>"
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = ""
    for row in rows:
        cells = "".join(f"<td>{escape(_fmt(c))}</td>" for c in row)
        body += f"<tr>{cells}</tr>"
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
