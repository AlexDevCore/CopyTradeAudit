"""Tests for price-aware skill: favourite-buyers must not look strong."""

from datetime import datetime
from decimal import Decimal

import pytest
from src.domain.models import Decision, Side
from src.scoring.skill import decision_roi, skill_from_decisions

T0 = datetime(2026, 1, 1)


def dec(market, direction, entry, seq=0):
    return Decision(
        wallet="0x1",
        market_id=market,
        direction=direction,
        opened_at=T0,
        entry_price=Decimal(entry),
        peak_shares=Decimal(100),
        seq=seq,
    )


def test_decision_roi_rewards_cheap_entry():
    # Favourite bought at 0.95 and won -> tiny ROI.
    assert decision_roi(dec("m", Side.YES, "0.95"), Side.YES) == pytest.approx(
        0.05263, rel=1e-3
    )
    # Value bought at 0.55 and won -> large ROI.
    assert decision_roi(dec("m", Side.YES, "0.55"), Side.YES) == pytest.approx(
        0.81818, rel=1e-3
    )
    # Any loss -> -1.0 regardless of entry.
    assert decision_roi(dec("m", Side.YES, "0.55"), Side.NO) == -1.0


def test_skill_counts_and_mean_roi():
    decisions = [
        dec("m1", Side.YES, "0.55", 0),
        dec("m2", Side.NO, "0.40", 1),
        dec("m3", Side.YES, "0.60", 2),
    ]
    outcomes = {"m1": Side.YES, "m2": Side.NO, "m3": Side.NO}
    skill = skill_from_decisions("0x1", "politics", decisions, outcomes)
    assert (skill.wins, skill.losses) == (2, 1)
    # ROIs: (1-.55)/.55, (payoff for NO@0.40 correct -> NO token entry 0.40) ...
    # m2 direction NO, entry 0.40 (NO token), outcome NO -> win -> (1-.40)/.40 = 1.5
    # m3 YES @0.60 lost -> -1
    expected = ((0.45 / 0.55) + (0.60 / 0.40) + (-1.0)) / 3
    assert skill.mean_roi == pytest.approx(expected, rel=1e-6)


def test_favourite_buyer_is_excluded_by_roi_floor():
    fav = skill_from_decisions(
        "fav",
        "politics",
        [dec(f"m{i}", Side.YES, "0.95", i) for i in range(30)],
        {f"m{i}": Side.YES for i in range(30)},
    )
    value = skill_from_decisions(
        "val",
        "politics",
        [dec(f"n{i}", Side.YES, "0.55", i) for i in range(30)],
        {f"n{i}": Side.YES for i in range(30)},
    )
    # Same perfect win rate, but the favourite-buyer's edge is ~0.
    assert fav.wins == value.wins == 30
    assert fav.mean_roi < 0.10 < value.mean_roi
    assert fav.is_pool_eligible(min_resolved=30, min_mean_roi=0.10) is False
    assert value.is_pool_eligible(min_resolved=30, min_mean_roi=0.10) is True
    # ROI breaks the Wilson tie in the value trader's favour.
    assert value.rank_key() > fav.rank_key()
