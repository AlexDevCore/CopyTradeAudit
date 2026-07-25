"""Run the copy strategy against benchmarks on a synthetic world and report.

Usage: python -m src.backtest.experiments
Prints a metrics table for an inefficient market (edge should exist) and an
efficient one (edge should vanish). Synthetic only — proves the harness, not
real profitability.
"""

from __future__ import annotations

from datetime import timedelta

from src.backtest.harness import RunConfig, run_benchmark, run_copy_strategy
from src.backtest.metrics import Metrics, summarize
from src.backtest.synthetic import DT0, make_world

_BENCH = ("random", "always_yes", "majority", "market_favorite")


def run_all(efficiency: float, *, seed: int = 0) -> dict[str, Metrics]:
    data = make_world(seed=seed, efficiency=efficiency)
    cfg = RunConfig(
        start=DT0 + timedelta(days=120),
        end=DT0 + timedelta(days=230),
        latency_sec=90,
    )
    out: dict[str, Metrics] = {
        "copy_strategy": summarize(run_copy_strategy(data, cfg)),
    }
    for kind in _BENCH:
        out[kind] = summarize(run_benchmark(data, cfg, kind))
    return out


def _fmt(m: Metrics) -> str:
    return (
        f"n={m.n_trades:4d} ev={m.n_events:3d}  "
        f"mean_pnl/sh={m.mean_pnl_per_share:+.4f}  "
        f"CI[{m.ci_low:+.4f},{m.ci_high:+.4f}]  "
        f"{'EDGE' if m.ci_excludes_zero and m.mean_pnl_per_share > 0 else 'no-edge'}  "
        f"wr={m.win_rate:.2f} pf={m.profit_factor:.2f} top5={m.top5_share:.2f}"
    )


def main() -> None:
    for eff, label in (
        (0.3, "INEFFICIENT price (efficiency=0.3)"),
        (1.0, "EFFICIENT price (efficiency=1.0)"),
    ):
        print(f"\n=== {label} ===")
        for name, m in run_all(eff).items():
            print(f"{name:16s} {_fmt(m)}")


if __name__ == "__main__":
    main()
