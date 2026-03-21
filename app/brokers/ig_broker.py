"""
ig_broker.py — IG Markets implementation of BaseBroker.

IG Markets REST API:
  - Base URL: https://api.ig.com/gateway/deal
  - Authentication: POST /session → CST + X-SECURITY-TOKEN headers
  - M30 resolution: "MINUTE_30"

Documentation: https://labs.ig.com/rest-trading-api-reference
"""
import logging
from typing import List

import httpx

from brokers.base_broker import BaseBroker, BrokerError

logger = logging.getLogger(__name__)

IG_BASE_URL = "https://api.ig.com/gateway/deal"


class IGBroker(BaseBroker):

    def __init__(self, api_key: str, identifier: str, password: str, demo: bool = True):
        self._api_key    = api_key
        self._identifier = identifier
        self._password   = password
        self._demo       = demo
        self._cst        = ""
        self._token      = ""
        self._client     = httpx.AsyncClient(timeout=30.0)

    def _headers(self) -> dict:
        return {
            "Content-Type":     "application/json; charset=UTF-8",
            "Accept":           "application/json; charset=UTF-8",
            "X-IG-API-KEY":     self._api_key,
            "CST":              self._cst,
            "X-SECURITY-TOKEN": self._token,
            "Version":          "2",
        }

    async def connect(self) -> None:
        payload = {
            "identifier":        self._identifier,
            "password":          self._password,
            "encryptedPassword": False,
        }
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept":       "application/json; charset=UTF-8",
            "X-IG-API-KEY": self._api_key,
            "Version":      "2",
        }
        try:
            resp = await self._client.post(
                f"{IG_BASE_URL}/session",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise BrokerError(
                f"IG connection failed ({e.response.status_code}): {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise BrokerError(f"Network error during IG connection: {e}") from e

        self._cst   = resp.headers.get("CST", "")
        self._token = resp.headers.get("X-SECURITY-TOKEN", "")
        logger.info("Connected to IG Markets (demo=%s)", self._demo)

    async def disconnect(self) -> None:
        try:
            await self._client.delete(
                f"{IG_BASE_URL}/session",
                headers=self._headers(),
            )
        except Exception as e:
            logger.warning("IG disconnect error: %s", e)
        finally:
            await self._client.aclose()
            logger.info("Disconnected from IG Markets")

    async def get_candles(self, symbol: str, count: int, timeframe: str = "MINUTE_30") -> List[dict]:
        url     = f"{IG_BASE_URL}/prices/{symbol}"
        params  = {"resolution": timeframe, "max": count, "pageSize": 0}
        headers = {**self._headers(), "Version": "3"}
        try:
            resp = await self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"get_candles {symbol} ({e.response.status_code})",
                request=e.request,
                response=e.response,
            ) from e

        candles = []
        for item in resp.json().get("prices", []):
            candles.append({
                "time":  item["snapshotTimeUTC"],
                "open":  float(item["openPrice"]["mid"] or 0),
                "high":  float(item["highPrice"]["mid"] or 0),
                "low":   float(item["lowPrice"]["mid"] or 0),
                "close": float(item["closePrice"]["mid"] or 0),
            })
        return candles

    async def get_account_balance(self) -> float:
        try:
            resp = await self._client.get(
                f"{IG_BASE_URL}/accounts",
                headers=self._headers(),
            )
            resp.raise_for_status()
            accounts = resp.json().get("accounts", [])
            if accounts:
                return float(accounts[0].get("balance", {}).get("available", 0))
        except Exception as e:
            logger.warning("get_account_balance failed: %s", e)
        return 0.0

    async def get_open_positions(self) -> List[dict]:
        try:
            resp = await self._client.get(
                f"{IG_BASE_URL}/positions/otc",
                headers={**self._headers(), "Version": "2"},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("get_open_positions failed: %s", e)
            return []

        positions = []
        for pos in resp.json().get("positions", []):
            positions.append({
                "epic":      pos.get("market", {}).get("epic", ""),
                "direction": pos.get("position", {}).get("direction", ""),
                "size":      float(pos.get("position", {}).get("size", 0)),
                "deal_id":   pos.get("position", {}).get("dealId", ""),
            })
        return positions

    async def open_long(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> None:
        await self._place_order(symbol, size, "BUY", sl, tp, **kwargs)

    async def open_short(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> None:
        await self._place_order(symbol, size, "SELL", sl, tp, **kwargs)

    async def _place_order(
        self,
        symbol:        str,
        size:          float,
        direction:     str,
        sl:            float,
        tp:            float,
        comment:       str = "",
        currency_code: str = "EUR",
        **kwargs,
    ) -> None:
        payload = {
            "epic":           symbol,
            "expiry":         "-",
            "direction":      direction,
            "size":           str(round(size, 2)),
            "orderType":      "MARKET",
            "timeInForce":    "FILL_OR_KILL",
            "guaranteedStop": False,
            "stopLevel":      str(round(sl, 2)),
            "limitLevel":     str(round(tp, 2)),
            "currencyCode":   currency_code,
        }
        try:
            resp = await self._client.post(
                f"{IG_BASE_URL}/positions/otc",
                json=payload,
                headers={**self._headers(), "Version": "2"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise BrokerError(
                f"{direction} order on {symbol} rejected ({e.response.status_code}): {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise BrokerError(f"Network error placing {direction} order on {symbol}: {e}") from e

        deal_ref = resp.json().get("dealReference", "?")
        logger.info("%s order on %s placed — dealRef: %s", direction, symbol, deal_ref)
