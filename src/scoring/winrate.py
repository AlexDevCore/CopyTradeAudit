"""Win-rate statistics.

We display the raw win rate but rank traders by the Wilson score interval's
lower bound, so that a small lucky sample (9/10) does not outrank a larger,
slightly-less-perfect one (160/200).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from src.domain.models import Decision, Side
from src.normalize.decisions import decision_correct


def raw_win_rate(wins: int, n: int) -> float:
    return wins / n if n else 0.0


def wilson_lower_bound(wins: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval for a binomial proportion.

    Returns 0.0 for an empty sample. This is the ranking statistic: it rewards
    both a high hit rate and a large, trustworthy sample.
    """
    if n <= 0:
        return 0.0
    phat = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = phat + z2 / (2 * n)
    margin = z * math.sqrt((phat * (1.0 - phat) + z2 / (4 * n)) / n)
    return (centre - margin) / denom


@dataclass(frozen=True)
class TraderScore:
    wallet: str
    category: str
    wins: int
    losses: int

    @property
    def n(self) -> int:
        return self.wins + self.losses

    @property
    def raw(self) -> float:
        return raw_win_rate(self.wins, self.n)

    def wilson(self, z: float = 1.96) -> float:
        return wilson_lower_bound(self.wins, self.n, z)


def score_from_decisions(
    wallet: str,
    category: str,
    decisions: Iterable[Decision],
    outcomes: Mapping[str, Side],
) -> TraderScore:
    """Count wins/losses over decisions that were held to resolution.

    ``outcomes`` maps market_id -> resolved Side. Decisions for markets not in
    ``outcomes`` (unresolved) and decisions not held to resolution are skipped.
    """
    wins = 0
    losses = 0
    for d in decisions:
        outcome = outcomes.get(d.market_id)
        if outcome is None:
            continue
        correct = decision_correct(d, outcome)
        if correct is None:
            continue
        if correct:
            wins += 1
        else:
            losses += 1
    return TraderScore(wallet=wallet, category=category, wins=wins, losses=losses)
