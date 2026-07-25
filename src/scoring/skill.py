"""Price-aware trader skill (fix a).

Win rate alone rewards "favourite buyers": someone who buys YES at 0.95 and is
right 95% of the time has a superb win rate and ~zero edge — impossible to copy
profitably. So we also measure realised ROI per decision, which is naturally
tiny for favourite-buying and large for genuine price edge. Ranking uses the
Wilson lower bound first (trust), ROI second (edge); ``min_mean_roi`` gates out
the favourite-buyers entirely.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from src.domain.models import Decision, Side
from src.normalize.decisions import decision_correct
from src.scoring.winrate import wilson_lower_bound


def decision_roi(decision: Decision, outcome: Side) -> float | None:
    """Realised ROI of a held-to-resolution decision.

    Payoff is 1 if the direction matched the outcome, else 0. Entry price is in
    the direction's own token, so ROI = (payoff - entry) / entry. Returns None
    for decisions not held to resolution (they are not counted here).
    """
    correct = decision_correct(decision, outcome)
    if correct is None:
        return None
    entry = float(decision.entry_price)
    if entry <= 0.0:
        return None
    payoff = 1.0 if correct else 0.0
    return (payoff - entry) / entry


@dataclass(frozen=True)
class TraderSkill:
    wallet: str
    category: str
    wins: int
    losses: int
    mean_roi: float  # price-aware edge per held-to-resolution decision

    @property
    def n(self) -> int:
        return self.wins + self.losses

    @property
    def raw(self) -> float:
        return self.wins / self.n if self.n else 0.0

    def wilson(self, z: float = 1.96) -> float:
        return wilson_lower_bound(self.wins, self.n, z)

    def rank_key(self, z: float = 1.96) -> tuple[float, float]:
        """Sort DESC by this: Wilson lower bound first, then mean ROI."""
        return (self.wilson(z), self.mean_roi)

    def is_pool_eligible(self, min_resolved: int, min_mean_roi: float) -> bool:
        return self.n >= min_resolved and self.mean_roi >= min_mean_roi


def skill_from_decisions(
    wallet: str,
    category: str,
    decisions: Iterable[Decision],
    outcomes: Mapping[str, Side],
) -> TraderSkill:
    wins = 0
    losses = 0
    roi_sum = 0.0
    roi_count = 0
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
        roi = decision_roi(d, outcome)
        if roi is not None:
            roi_sum += roi
            roi_count += 1
    mean_roi = roi_sum / roi_count if roi_count else 0.0
    return TraderSkill(
        wallet=wallet,
        category=category,
        wins=wins,
        losses=losses,
        mean_roi=mean_roi,
    )
