"""Out-of-sample pool validation (fix c).

Selecting the top traders from a large population overfits: some "skill" is
luck. To catch it we split each trader's decisions in time, rank on the earlier
half (train) and again on the later half (test), and measure how much the top-N
pool overlaps. Low overlap = the ranking does not generalise, so the pool should
be trusted less (or the sample requirement raised).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from src.domain.models import Decision, Side
from src.scoring.skill import TraderSkill, skill_from_decisions


def split_by_time(
    decisions: Sequence[Decision], at: datetime
) -> tuple[list[Decision], list[Decision]]:
    """Partition decisions into (train = opened before ``at``, test = at/after)."""
    train = [d for d in decisions if d.opened_at < at]
    test = [d for d in decisions if d.opened_at >= at]
    return train, test


def median_open_time(decisions: Sequence[Decision]) -> datetime | None:
    times = sorted(d.opened_at for d in decisions)
    if not times:
        return None
    return times[len(times) // 2]


def top_wallets(skills: Iterable[TraderSkill], k: int, z: float = 1.96) -> list[str]:
    ranked = sorted(skills, key=lambda s: s.rank_key(z), reverse=True)
    return [s.wallet for s in ranked[:k]]


def pool_overlap(train_top: Sequence[str], test_top: Sequence[str]) -> float:
    """Jaccard overlap between two top-N wallet sets, in [0, 1]."""
    a, b = set(train_top), set(test_top)
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def validate_pool(
    decisions_by_wallet: Mapping[str, Sequence[Decision]],
    outcomes: Mapping[str, Side],
    *,
    category: str,
    split_at: datetime,
    top_k: int,
    z: float = 1.96,
) -> float:
    """Return the top-``top_k`` pool overlap between train and test halves."""
    train_skills: list[TraderSkill] = []
    test_skills: list[TraderSkill] = []
    for wallet, decisions in decisions_by_wallet.items():
        train, test = split_by_time(decisions, split_at)
        train_skills.append(skill_from_decisions(wallet, category, train, outcomes))
        test_skills.append(skill_from_decisions(wallet, category, test, outcomes))
    return pool_overlap(
        top_wallets(train_skills, top_k, z), top_wallets(test_skills, top_k, z)
    )
