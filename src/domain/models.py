"""Core value objects for CopyTradeAudit.

Everything a trader does is normalised to a *YES-equivalent* signed quantity so
that a position in one market collapses to a single scalar: net YES-equivalent
shares. Economically, buying NO is selling YES, and NO@p == YES@(1 - p). This
keeps the "one decision = net exposure" logic simple and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Side(str, Enum):
    YES = "YES"
    NO = "NO"


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class TraderTrade:
    """A single observed on-chain trade by a tracked wallet in one market.

    Stored already normalised to YES-equivalent terms:
      - ``yes_delta``  signed change to net YES-equivalent exposure
                       (+ increases YES exposure, - increases NO exposure)
      - ``yes_price``  the YES-equivalent price in [0, 1] of that delta.
    Use :meth:`from_token_trade` to build one from raw (side, action) data.
    """

    wallet: str
    market_id: str
    timestamp: datetime
    yes_delta: Decimal
    yes_price: Decimal
    is_taker: bool | None = None  # None = classification unknown

    @classmethod
    def from_token_trade(
        cls,
        *,
        wallet: str,
        market_id: str,
        side: Side,
        action: Action,
        shares: Decimal,
        price: Decimal,
        timestamp: datetime,
        is_taker: bool | None = None,
    ) -> TraderTrade:
        """Build from a raw per-token trade (buy/sell of YES or NO @ price)."""
        sign = 1 if side is Side.YES else -1
        if action is Action.SELL:
            sign = -sign
        yes_delta = Decimal(sign) * shares
        yes_price = price if side is Side.YES else (Decimal(1) - price)
        return cls(
            wallet=wallet,
            market_id=market_id,
            timestamp=timestamp,
            yes_delta=yes_delta,
            yes_price=yes_price,
            is_taker=is_taker,
        )


@dataclass(frozen=True)
class Level:
    """One price level of an order book: ``size`` shares offered at ``price``."""

    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class Orderbook:
    """Order book snapshot for a single token at one instant.

    ``asks`` ascending by price (what you pay to BUY), ``bids`` descending
    (what you receive to SELL).
    """

    market_id: str
    timestamp: datetime
    asks: tuple[Level, ...]
    bids: tuple[Level, ...]

    @property
    def best_ask(self) -> Decimal | None:
        return self.asks[0].price if self.asks else None

    @property
    def best_bid(self) -> Decimal | None:
        return self.bids[0].price if self.bids else None

    @property
    def mid(self) -> Decimal | None:
        if self.best_ask is None or self.best_bid is None:
            return None
        return (self.best_ask + self.best_bid) / Decimal(2)


class DecisionState(str, Enum):
    OPEN = "OPEN"  # still held in its direction (open at resolution)
    CLOSED = "CLOSED"  # net exposure returned to ~0 before resolution
    REVERSED = "REVERSED"  # position flipped to the opposite direction


@dataclass
class Decision:
    """One independent directional prediction by a wallet in one market.

    Not one per trade — many same-direction trades collapse into a single
    Decision. A sign flip of net exposure closes this one and opens a new one.
    """

    wallet: str
    market_id: str
    direction: Side
    opened_at: datetime
    entry_price: Decimal  # avg price in the direction's own token, [0, 1]
    peak_shares: Decimal  # max |net| while open — conviction/size proxy
    seq: int  # order among this wallet's decisions in the market
    is_reversal: bool = False
    closed_at: datetime | None = None
    state: DecisionState = DecisionState.OPEN

    @property
    def open_at_resolution(self) -> bool:
        """True if held to resolution (counts toward held-to-resolution win rate)."""
        return self.state is DecisionState.OPEN
