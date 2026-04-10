"""
alpaca_broker.py — Alpaca Markets implementation of BaseBroker.

Alpaca Trading API:
  - Trading URL (paper): https://paper-api.alpaca.markets
  - Trading URL (live):  https://api.alpaca.markets
  - Data URL:            https://data.alpaca.markets
  - Authentication: APCA-API-KEY-ID + APCA-API-SECRET-KEY headers
  - M30 resolution: "30Min"

Documentation: https://docs.alpaca.markets/reference/trading-api
"""
import logging
from typing import List

import httpx

from brokers.base_broker import BaseBroker, BrokerError

logger = logging.getLogger(__name__)

ALPACA_LIVE_URL  = "https://api.alpaca.markets"
ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"
ALPACA_DATA_URL  = "https://data.alpaca.markets"


class AlpacaBroker(BaseBroker):

    def __init__(self, api_key: str, api_secret: str, demo: bool = True):
        self._api_key    = api_key
        self._api_secret = api_secret
        self._demo       = demo
        self._base_url   = ALPACA_PAPER_URL if demo else ALPACA_LIVE_URL
        self._client     = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        return False

    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID":     self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
            "Content-Type":        "application/json",
            "Accept":              "application/json",
        }

    async def connect(self) -> None:
        """Validate credentials by fetching account info (stateless API — no session)."""
        try:
            resp = await self._client.get(
                f"{self._base_url}/v2/account",
                headers=self._headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise BrokerError(
                f"Alpaca connection failed ({e.response.status_code}): {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise BrokerError(f"Network error during Alpaca connection: {e}") from e
        logger.info("Connected to Alpaca Markets (demo=%s)", self._demo)

    async def disconnect(self) -> None:
        await self._client.aclose()
        logger.info("Disconnected from Alpaca Markets")

    async def get_candles(self, symbol: str, count: int, timeframe: str = "30Min") -> List[dict]:
        url    = f"{ALPACA_DATA_URL}/v2/stocks/bars"
        params = {
            "symbols":   symbol,
            "timeframe": timeframe,
            "limit":     count,
            "sort":      "asc",
        }
        try:
            resp = await self._client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise BrokerError(
                f"get_candles {symbol} failed ({e.response.status_code}): {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise BrokerError(f"Network error fetching candles for {symbol}: {e}") from e

        bars = resp.json().get("bars", {}).get(symbol, [])
        return [
            {
                "time":  bar["t"],
                "open":  float(bar["o"]),
                "high":  float(bar["h"]),
                "low":   float(bar["l"]),
                "close": float(bar["c"]),
            }
            for bar in bars
        ]

    async def get_account_balance(self) -> float:
        try:
            resp = await self._client.get(
                f"{self._base_url}/v2/account",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return float(resp.json().get("portfolio_value", 0))
        except Exception as e:
            logger.warning("get_account_balance failed: %s", e)
        return 0.0

    async def get_open_positions(self) -> List[dict]:
        try:
            resp = await self._client.get(
                f"{self._base_url}/v2/positions",
                headers=self._headers(),
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("get_open_positions failed: %s", e)
            return []

        positions = []
        for pos in resp.json():
            positions.append({
                "epic":      pos.get("symbol", ""),
                "direction": "BUY" if pos.get("side") == "long" else "SELL",
                "size":      float(pos.get("qty", 0)),
                "deal_id":   pos.get("asset_id", ""),
            })
        return positions

    async def open_long(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> None:
        await self._place_order(symbol, size, "buy", sl, tp)

    async def open_short(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> None:
        await self._place_order(symbol, size, "sell", sl, tp)

    async def _place_order(
        self,
        symbol: str,
        size:   float,
        side:   str,
        sl:     float,
        tp:     float,
    ) -> None:
        payload = {
            "symbol":        symbol,
            "qty":           str(round(size, 2)),
            "side":          side,
            "type":          "market",
            "time_in_force": "gtc",
            "order_class":   "bracket",
            "take_profit": {
                "limit_price": str(round(tp, 2)),
            },
            "stop_loss": {
                "stop_price": str(round(sl, 2)),
            },
        }
        try:
            resp = await self._client.post(
                f"{self._base_url}/v2/orders",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise BrokerError(
                f"{side} order on {symbol} rejected ({e.response.status_code}): {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise BrokerError(f"Network error placing {side} order on {symbol}: {e}") from e

        order_id = resp.json().get("id", "?")
        logger.info("%s order on %s placed — orderId: %s", side, symbol, order_id)
