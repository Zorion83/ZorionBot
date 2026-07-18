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
import math
from datetime import datetime, timedelta, timezone
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

    async def get_candles(self, symbol: str, count: int, timeframe: str = "30Min",
                          start: str = "") -> List[dict]:
        """
        Fetch candles for a symbol.

        - Without `start`: fetches the most recent `count` bars (sort=desc then reversed).
        - With `start`: fetches up to `count` bars AFTER the given ISO timestamp (sort=asc).
        """
        is_crypto = "/" in symbol
        if is_crypto:
            url = f"{ALPACA_DATA_URL}/v1beta3/crypto/us/bars"
            tf  = "30T"   # crypto uses T (minutes) notation
        else:
            url = f"{ALPACA_DATA_URL}/v2/stocks/bars"
            tf  = timeframe

        if start:
            # Incremental / catch-up fetch: bars starting from `start` onwards
            params = {
                "symbols":   symbol,
                "timeframe": tf,
                "limit":     count,
                "start":     start,
                "sort":      "asc",
            }
        else:
            # Full fetch: most recent `count` bars.
            # Alpaca returns 0 bars without a `start` parameter (defaults to today only).
            # Fix: use a wide lookback window + sort=desc to always get the N most recent bars.
            lookback_days = 60 if is_crypto else 400   # crypto 24/7, stocks weekends/holidays
            far_back = (datetime.now(timezone.utc) - timedelta(days=lookback_days))
            params = {
                "symbols":   symbol,
                "timeframe": tf,
                "limit":     count,
                "start":     far_back.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sort":      "desc",
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
        if not start:
            bars = list(reversed(bars))   # desc → asc (oldest first)
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

    async def get_account_info(self) -> dict:
        """Single call returning portfolio_value (equity) and cash (actual spendable USD).

        Note: Alpaca's buying_power = 2× cash for margin accounts — do NOT use it
        for notional caps. Use cash (= non_marginable_buying_power) instead, which
        is the real USD available to spend on any order including crypto.
        """
        try:
            resp = await self._client.get(
                f"{self._base_url}/v2/account",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "balance":       float(data.get("portfolio_value", 0)),
                "buying_power":  float(data.get("cash", 0)),
            }
        except Exception as e:
            logger.warning("get_account_info failed: %s", e)
        return {"balance": 0.0, "buying_power": 0.0}

    async def get_account_balance(self) -> float:
        """Kept for backward compatibility — prefer get_account_info()."""
        return (await self.get_account_info())["balance"]

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
            symbol = pos.get("symbol", "")
            # Alpaca returns crypto position symbols without the slash (e.g. "BTCUSD"),
            # while orders/candles/asset_config use "BTC/USD". Re-insert it so this
            # epic matches the one used everywhere else (open_epics check, signal cache).
            if pos.get("asset_class") == "crypto" and "/" not in symbol and symbol.endswith("USD"):
                symbol = symbol[:-3] + "/USD"
            positions.append({
                "epic":          symbol,
                "direction":     "BUY" if pos.get("side") == "long" else "SELL",
                "size":          float(pos.get("qty", 0)),
                "deal_id":       pos.get("asset_id", ""),
                "entry_price":   float(pos.get("avg_entry_price", 0)),
                "current_price": float(pos.get("current_price", 0)),
                "unrealized_pl": float(pos.get("unrealized_pl", 0)),
            })
        return positions

    async def get_closed_orders_since(self, symbol: str, after_iso: str) -> List[dict]:
        """Fetch filled orders for a symbol after the given ISO timestamp."""
        try:
            resp = await self._client.get(
                f"{self._base_url}/v2/orders",
                params={
                    "status":    "filled",
                    "symbols":   symbol,
                    "after":     after_iso,
                    "limit":     10,
                    "direction": "desc",
                },
                headers=self._headers(),
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("get_closed_orders_since failed for %s: %s", symbol, e)
            return []

        return [
            {
                "symbol":            o.get("symbol", ""),
                "side":              o.get("side", ""),
                "filled_avg_price":  float(o.get("filled_avg_price") or 0),
                "filled_qty":        float(o.get("filled_qty") or 0),
            }
            for o in resp.json()
            if o.get("status") == "filled"
        ]

    async def _get_latest_price(self, symbol: str) -> float:
        """Fetch the latest trade price for a symbol (stock or crypto)."""
        is_crypto = "/" in symbol
        try:
            if is_crypto:
                resp = await self._client.get(
                    f"{ALPACA_DATA_URL}/v1beta3/crypto/us/latest/trades",
                    params={"symbols": symbol},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return float(resp.json().get("trades", {}).get(symbol, {}).get("p", 0))
            else:
                resp = await self._client.get(
                    f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/trades/latest",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return float(resp.json().get("trade", {}).get("p", 0))
        except Exception as e:
            logger.warning("_get_latest_price(%s) failed: %s", symbol, e)
            return 0.0

    async def open_long(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> None:
        await self._place_order(symbol, size, "buy", sl, tp)

    async def open_short(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> None:
        await self._place_order(symbol, size, "sell", sl, tp)

    async def close_position(self, symbol: str) -> None:
        """
        Liquidate the entire open position for a symbol at market price.
        Used for crypto positions where SL/TP are managed by the bot's main loop
        (Alpaca does not support bracket orders for crypto).
        """
        # Alpaca's /v2/positions endpoint returns crypto symbols without the
        # slash (e.g. "BTCUSD"), and DELETE expects that same bare form —
        # not a URL-encoded "BTC%2FUSD", which 404s.
        path_symbol = symbol.replace("/", "")
        try:
            resp = await self._client.delete(
                f"{self._base_url}/v2/positions/{path_symbol}",
                headers=self._headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise BrokerError(
                f"close_position {symbol} rejected ({e.response.status_code}): {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise BrokerError(f"Network error closing position {symbol}: {e}") from e
        logger.info("Position %s liquidated via DELETE /v2/positions", symbol)

    async def _place_order(
        self,
        symbol: str,
        size:   float,
        side:   str,
        sl:     float,
        tp:     float,
    ) -> None:
        is_crypto = "/" in symbol

        if is_crypto:
            # ── Crypto path ───────────────────────────────────────────
            # Alpaca does NOT support bracket orders (order_class=otoco) for crypto.
            # Use a simple market order; TP/SL are enforced by the bot's monitoring loop.
            # Crypto supports fractional quantities — do NOT floor.
            qty_crypto = round(size, 6)
            if qty_crypto <= 0:
                raise BrokerError(
                    f"Computed qty <= 0 for {symbol} (size={size}) — skipping order"
                )
            payload = {
                "symbol":        symbol,
                "qty":           str(qty_crypto),
                "side":          side,
                "type":          "market",
                "time_in_force": "gtc",
                "order_class":   "simple",
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
            logger.info(
                "%s (crypto) order on %s placed — orderId: %s | SL=%.2f TP=%.2f [bot-managed]",
                side, symbol, order_id, sl, tp,
            )
            return

        # ── Stock path ────────────────────────────────────────────────
        # Alpaca Paper Trading rejects bracket orders (GTC or otherwise) with
        # error 42210000 for various internal reasons (fractional notional,
        # margin checks, etc.). Use a simple market order instead; TP/SL are
        # managed by the bot's monitoring loop (same approach as crypto).
        #
        # Stocks require whole-share quantities (no fractional GTC).
        qty = math.floor(size)
        if qty < 1:
            raise BrokerError(f"Computed qty < 1 for {symbol} (size={size:.4f}) — skipping order")

        payload = {
            "symbol":        symbol,
            "qty":           str(qty),
            "side":          side,
            "type":          "market",
            "time_in_force": "day",
            "order_class":   "simple",
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
        logger.info(
            "%s (stock) order on %s placed — orderId: %s | SL=%.2f TP=%.2f [bot-managed]",
            side, symbol, order_id, sl, tp,
        )
