"""Tests for out-of-sample pool validation."""

from datetime import datetime, timedelta
from decimal import Decimal

from src.domain.models import Decision, Side
from src.scoring.validation import (
    pool_overlap,
    split_by_time,
    top_wallets,
    validate_pool,
)

T0 = datetime(2026, 1, 1)


def dec(wallet, market, direction, entry, minute):
    return Decision(
        wallet=wallet,
        market_id=market,
        direction=direction,
        opened_at=T0 + timedelta(minutes=minute),
        entry_price=Decimal(entry),
        peak_shares=Decimal(100),
        seq=0,
    )


def test_split_by_time():
    ds = [dec("a", "m1", Side.YES, "0.5", 0), dec("a", "m2", Side.YES, "0.5", 10)]
    train, test = split_by_time(ds, T0 + timedelta(minutes=5))
    assert len(train) == 1 and len(test) == 1


def test_pool_overlap_math():
    assert pool_overlap(["a", "b"], ["a", "b"]) == 1.0
    assert pool_overlap(["a", "b"], ["c", "d"]) == 0.0
    assert pool_overlap(["a", "b"], ["b", "c"]) == 1 / 3
    assert pool_overlap([], []) == 1.0


def test_validate_pool_flags_overfit():
    # "lucky" tops the early half but collapses later; "steady" is consistent.
    outcomes = {}
    decisions_by_wallet = {"lucky": [], "steady": [], "filler": []}

    def add(wallet, market, direction, entry, minute, outcome):
        decisions_by_wallet[wallet].append(
            dec(wallet, market, direction, entry, minute)
        )
        outcomes[market] = outcome

    # Train window (minutes < 100): lucky wins everything cheap, steady decent.
    for i in range(6):
        add("lucky", f"L{i}", Side.YES, "0.50", i, Side.YES)  # all win
        add(
            "steady", f"S{i}", Side.YES, "0.50", i, Side.YES if i % 2 else Side.NO
        )  # 50/50
        add("filler", f"F{i}", Side.YES, "0.50", i, Side.NO)  # all lose
    # Test window (minutes >= 100): lucky reverts, steady still decent, filler improves.
    for i in range(6):
        add("lucky", f"L1{i}", Side.YES, "0.50", 100 + i, Side.NO)  # all lose
        add(
            "steady",
            f"S1{i}",
            Side.YES,
            "0.50",
            100 + i,
            Side.YES if i % 2 else Side.NO,
        )
        add("filler", f"F1{i}", Side.YES, "0.50", 100 + i, Side.YES)  # all win

    overlap = validate_pool(
        decisions_by_wallet,
        outcomes,
        category="politics",
        split_at=T0 + timedelta(minutes=100),
        top_k=1,
    )
    # Train top is "lucky"; test top is not -> zero overlap signals overfit.
    assert overlap == 0.0


def test_top_wallets_orders_by_rank():
    from src.scoring.skill import TraderSkill

    strong = TraderSkill("strong", "politics", wins=160, losses=40, mean_roi=0.3)
    weak = TraderSkill("weak", "politics", wins=5, losses=5, mean_roi=0.1)
    assert top_wallets([weak, strong], 1) == ["strong"]
