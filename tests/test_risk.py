"""Tests for deterministic risk limits."""

from decimal import Decimal

from src.risk.limits import (
    check_trade,
    is_data_stale,
    position_size,
    within_correlated_group_limit,
)

BAL = Decimal(1000)


def test_position_size_uses_bet_fraction_capped():
    # bet 3% = 30, cap 5% = 50 -> 30.
    assert position_size(BAL) == Decimal("30.00")


def test_correlated_group_limit():
    # cap = 10% * 1000 = 100.
    assert within_correlated_group_limit(Decimal(50), Decimal(30), BAL) is True
    assert within_correlated_group_limit(Decimal(80), Decimal(30), BAL) is False


def test_is_data_stale():
    assert is_data_stale(400) is True
    assert is_data_stale(60) is False


def test_check_trade_approves_fresh_within_limits():
    result = check_trade(BAL, group_exposure=Decimal(0), data_age_sec=60)
    assert result.approved is True
    assert result.size == Decimal("30.00")


def test_check_trade_sizes_down_to_group_room():
    # group at 90 -> room 10 -> approve sized-down 10.
    result = check_trade(BAL, group_exposure=Decimal(90), data_age_sec=60)
    assert result.approved is True
    assert result.size == Decimal(10)
    assert "sized down" in result.reason


def test_check_trade_refuses_when_group_full():
    result = check_trade(BAL, group_exposure=Decimal(100), data_age_sec=60)
    assert result.approved is False


def test_check_trade_refuses_stale():
    result = check_trade(BAL, group_exposure=Decimal(0), data_age_sec=400)
    assert result.approved is False
    assert "stale" in result.reason
