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
    pass


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
    async def get_candles(self, symbol: str, count: int, timeframe: str = "MINUTE_30") -> List[dict]:
        """
        Fetch the last `count` closed candles for the symbol.

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
    async def open_long(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> None:
        """
        Open a long (BUY) position.
        Raises BrokerError with descriptive message if the broker rejects the order.
        """

    @abstractmethod
    async def open_short(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> None:
        """
        Open a short (SELL) position.
        Raises BrokerError with descriptive message if the broker rejects the order.
        """
