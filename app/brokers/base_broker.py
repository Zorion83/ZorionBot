"""
base_broker.py — Abstract broker interface contract.

To add a new broker:
  1. Create brokers/<name>_broker.py
  2. Implement all abstract methods of BaseBroker
  3. Set BROKER=<name> in .env
"""
from abc import ABC, abstractmethod
from typing import List


class BrokerError(Exception):
    """Raised when the broker rejects or fails to execute an operation."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class BaseBroker(ABC):

    @abstractmethod
    async def connect(self) -> None:
        """
        Authenticate with the broker.
        Raises BrokerError if connection fails.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Cleanly close the broker session."""

    @abstractmethod
    async def get_candles(self, symbol: str, count: int, timeframe: str = "30Min",
                          start: str = "") -> List[dict]:
        """
        Fetch candles for the symbol.

        Without `start`: returns the most recent `count` bars.
        With `start` (ISO 8601): returns up to `count` bars AFTER that timestamp.

        Returns:
            List of dicts with keys:
              "time"  : str  (ISO 8601)
              "open"  : float
              "high"  : float
              "low"   : float
              "close" : float
        """

    @abstractmethod
    async def get_account_balance(self) -> float:
        """
        Return available account balance in account currency.
        Returns 0.0 on non-blocking error.
        """

    @abstractmethod
    async def get_open_positions(self) -> List[dict]:
        """
        Return currently open positions.

        Each dict contains at minimum:
          "epic":      str   — instrument identifier
          "direction": str   — "BUY" or "SELL"
          "size":      float — position size
          "deal_id":   str   — unique position identifier
        """

    @abstractmethod
    async def open_long(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> str:
        """
        Open a long (BUY) position.
        Returns the broker's identifier for the opened position (deal_id / order_id),
        or "" if the broker cannot report one.
        Raises BrokerError with descriptive message if the broker rejects the order.
        """

    @abstractmethod
    async def open_short(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> str:
        """
        Open a short (SELL) position.
        Returns the broker's identifier for the opened position (deal_id / order_id),
        or "" if the broker cannot report one.
        Raises BrokerError with descriptive message if the broker rejects the order.
        """

    @abstractmethod
    async def close_position(self, symbol: str, deal_id: str = None) -> None:
        """
        Close an open position at market price (full liquidation).
        If `deal_id` is given, target that specific position (required when several
        positions can be open on the same symbol). If omitted, implementations may
        close the first position found on `symbol`.
        Raises BrokerError if the broker rejects the close.
        """

    @abstractmethod
    async def amend_stop(self, deal_id: str, new_sl: float) -> None:
        """
        Move the stop loss of an already-open position to `new_sl`, without closing it.
        Used to move a runner to breakeven once a sibling position's TP is hit.
        Raises BrokerError if the broker rejects the amendment or does not support it.
        """
