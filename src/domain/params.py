"""Strategy parameters — the §5 starting defaults, all tunable via config.

These are deliberately conservative. Nothing here is a promise; they gate when
the system is *allowed* to act and default heavily toward NO TRADE.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class StrategyParams:
    # --- decision detection (what counts as one independent decision) ---
    # Hard dust guard only. The real bar is market-relative (percentile below):
    # a flat $100 floor discards whole categories rather than filtering their
    # noise — 95% of real sports trades are smaller than $100.
    min_notional_usd: Decimal = Decimal(10)
    min_fraction_of_typical: Decimal = Decimal("0.25")
    # A position counts as a decision when it is in the top (1-p) of that
    # market's own trade-size distribution. 0.90 = "among the biggest 10% here".
    market_size_percentile: float = 0.90

    # --- trader eligibility ---
    min_resolved_markets: int = 30
    history_days: int = 180

    # --- polling / detection latency ---
    poll_interval_sec: int = 90
    reaction_latency_sec: int = 5
    data_staleness_sec: int = 300  # older than this -> NO TRADE

    # --- virtual portfolio sizing / risk ---
    starting_balance_usd: Decimal = Decimal(1000)
    bet_fraction: Decimal = Decimal("0.03")
    max_position_fraction: Decimal = Decimal("0.05")
    max_correlated_group_fraction: Decimal = Decimal("0.10")

    # --- signal gate ---
    consensus_threshold: float = 0.60
    min_edge_after_costs: float = 0.02
    min_signal_contributors: int = 2  # fewer -> NO TRADE
    evidence_shrinkage_k: float = 20.0  # decisions needed to earn full evidence weight
    freshness_tau_days: float = 30.0  # exponential staleness decay of a trader's view
    min_mean_roi: float = (
        0.02  # fix (a): price-aware skill floor (excludes favourite-buyers)
    )

    # --- scoring ---
    wilson_z: float = 1.96

    # --- provenance ---
    strategy_version: str = "v0.0"  # stamped on every audited paper trade


DEFAULTS = StrategyParams()
