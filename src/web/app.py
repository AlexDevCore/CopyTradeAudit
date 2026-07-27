"""FastAPI app: five read-only screens over the paper-mode state.

Localhost only. Read-only — no route mutates state or places any order. The mode
badge is driven by the service and defaults to PAPER.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from src.web import render
from src.web.service import DashboardService


def create_app(service: DashboardService) -> FastAPI:
    app = FastAPI(title="CopyTradeAudit", docs_url=None, redoc_url=None)
    mode = service.mode

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        d = service.dashboard()
        wr = d["strategy_win_rate"]
        body = render.cards(
            [
                ("Mode", d["mode"]),
                ("Starting balance", d["starting_balance"]),
                ("Free balance", d["free_balance"]),
                ("Open positions value", d["open_value"]),
                ("Open positions", d["open_positions"]),
                ("Realized PnL", d["realized_pnl"]),
                ("Unrealized PnL", d["unrealized_pnl"]),
                ("Equity", d["equity"]),
                ("Net result (after costs)", d["net_result"]),
                ("Max drawdown", d["max_drawdown"]),
                ("Strategy win rate", "—" if wr is None else f"{wr:.0%}"),
                ("Resolved trades", d["resolved_trades"]),
            ]
        )
        feeds = d["feeds"] or {"(none)": "—"}
        body += "<h1>Data feeds</h1>" + render.table(
            ["Feed", "Status"], [[k, v] for k, v in feeds.items()]
        )
        return render.layout("Dashboard", "/", body, mode=mode)

    @app.get("/markets", response_class=HTMLResponse)
    def markets() -> str:
        rows = [
            [
                m.get("name"),
                m.get("category"),
                m.get("yes_price"),
                m.get("no_price"),
                m.get("spread"),
                m.get("liquidity"),
                m.get("time_to_resolution"),
                m.get("consensus_score"),
                m.get("experts"),
                m.get("edge_after_costs"),
                m.get("decision"),
                m.get("explanation"),
            ]
            for m in service.markets()
        ]
        body = render.table(
            [
                "Market",
                "Category",
                "YES",
                "NO",
                "Spread",
                "Liquidity",
                "Time left",
                "Consensus",
                "Experts",
                "Edge (net)",
                "Decision",
                "Explanation",
            ],
            rows,
        )
        return render.layout("Markets", "/markets", body, mode=mode)

    @app.get("/traders", response_class=HTMLResponse)
    def traders() -> str:
        rows = [
            [
                t.get("address"),
                t.get("category"),
                t.get("wins"),
                t.get("losses"),
                t.get("raw_win_rate"),
                t.get("adjusted_win_rate"),
                t.get("markets"),
                t.get("roi"),
                t.get("pnl"),
                t.get("drawdown"),
                t.get("typical_entry"),
                t.get("maker_taker"),
                t.get("tracked_positions"),
                t.get("reason"),
            ]
            for t in service.traders()
        ]
        body = render.table(
            [
                "Address",
                "Category",
                "Wins",
                "Losses",
                "Raw WR",
                "Adj WR",
                "Markets",
                "ROI",
                "PnL",
                "Drawdown",
                "Typ. entry",
                "Maker/Taker",
                "Tracked",
                "Included because",
            ],
            rows,
        )
        return render.layout("Traders", "/traders", body, mode=mode)

    @app.get("/portfolio", response_class=HTMLResponse)
    def portfolio() -> str:
        view = service.portfolio_view()
        open_rows = [
            [
                r["market_id"],
                r["direction"],
                r["shares"],
                r["avg_entry_price"],
                r["cost_basis"],
                r["fee"],
                r["slippage"],
                r["consensus_score"],
                r["entry_reason"],
            ]
            for r in view["open"]
        ]
        closed_rows = [
            [
                r["market_id"],
                r["direction"],
                r["outcome"],
                r["shares"],
                r["signal_price"],
                r["fill_price"],
                r["trader_price"],
                r["fee"],
                r["slippage"],
                r["latency_sec"],
                r["realized_pnl"],
                r["hold_to_resolution_pnl"],
                r["exit_reason"],
            ]
            for r in view["closed"]
        ]
        body = "<h1>Open positions</h1>" + render.table(
            [
                "Market",
                "Dir",
                "Shares",
                "Entry",
                "Cost",
                "Fee",
                "Slip",
                "Consensus",
                "Entry reason",
            ],
            open_rows,
        )
        body += "<h1>Closed trades</h1>" + render.table(
            [
                "Market",
                "Dir",
                "Outcome",
                "Shares",
                "Signal px",
                "Fill px",
                "Trader px",
                "Fee",
                "Slip",
                "Latency s",
                "Realized PnL",
                "Hold-to-res PnL",
                "Exit reason",
            ],
            closed_rows,
        )
        return render.layout("Paper portfolio", "/portfolio", body, mode=mode)

    @app.get("/audit", response_class=HTMLResponse)
    def audit() -> str:
        rows = [
            [e["at"], e["kind"], e["market_id"], e["message"]]
            for e in service.audit_view()
        ]
        body = render.table(["Time", "Kind", "Market", "Message"], rows)
        return render.layout("Audit log", "/audit", body, mode=mode)

    return app


def main() -> None:
    import uvicorn

    from src.web.demo import build_demo_service

    uvicorn.run(create_app(build_demo_service()), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
