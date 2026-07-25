"""Tests for order-book execution: fees, slippage, partial fills."""

from decimal import Decimal

from src.domain.models import Level
from src.paper.execution import simulate_buy, simulate_sell

FEE = Decimal("0.01")


def lvl(price, size):
    return Level(price=Decimal(str(price)), size=Decimal(str(size)))


def test_buy_full_fill_single_level():
    fill = simulate_buy([lvl(0.50, 1000)], Decimal(100), fee_rate=FEE)
    assert fill.filled_fully is True
    assert fill.shares_filled == Decimal(100)
    assert fill.avg_price == Decimal("0.50")
    assert fill.notional == Decimal("50.00")
    assert fill.fee == Decimal("0.5000")
    assert fill.slippage == Decimal(0)
    assert fill.levels_used == 1


def test_buy_walks_multiple_levels_with_slippage():
    book = [lvl(0.50, 100), lvl(0.55, 100), lvl(0.60, 100)]
    fill = simulate_buy(book, Decimal(300), fee_rate=FEE)
    assert fill.filled_fully is True
    assert fill.shares_filled == Decimal(300)
    # avg = (0.50 + 0.55 + 0.60)*100 / 300 = 0.55
    assert fill.avg_price == Decimal("0.55")
    # slippage vs best ask 0.50
    assert fill.slippage == Decimal("0.05")
    assert fill.levels_used == 3


def test_buy_partial_fill_when_book_too_thin():
    book = [lvl(0.50, 100), lvl(0.55, 50)]
    fill = simulate_buy(book, Decimal(300), fee_rate=FEE)
    assert fill.filled_fully is False
    assert fill.shares_filled == Decimal(150)
    assert fill.levels_used == 2


def test_buy_empty_book_returns_zero_fill():
    fill = simulate_buy([], Decimal(100), fee_rate=FEE)
    assert fill.shares_filled == Decimal(0)
    assert fill.filled_fully is False
    assert fill.notional == Decimal(0)


def test_buy_zero_target_returns_zero_fill():
    fill = simulate_buy([lvl(0.50, 100)], Decimal(0), fee_rate=FEE)
    assert fill.shares_filled == Decimal(0)
    assert fill.filled_fully is False


def test_fee_applied_on_traded_notional():
    fill = simulate_buy([lvl(0.40, 1000)], Decimal(250), fee_rate=Decimal("0.02"))
    # notional = 250 * 0.40 = 100 ; fee = 2.00 ; total_cost = 102.00
    assert fill.notional == Decimal("100.00")
    assert fill.fee == Decimal("2.0000")
    assert fill.total_cost == Decimal("102.0000")


def test_sell_walks_bids_with_slippage():
    book = [lvl(0.60, 100), lvl(0.55, 100)]
    fill = simulate_sell(book, Decimal(200), fee_rate=FEE)
    assert fill.filled_fully is True
    # avg = (0.60 + 0.55)*100 / 200 = 0.575 ; slippage vs best bid 0.60 = 0.025
    assert fill.avg_price == Decimal("0.575")
    assert fill.slippage == Decimal("0.025")
