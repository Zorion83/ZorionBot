"""
ig_broker.py — IG Markets implementation of BaseBroker.

IG Markets REST API:
  - Base URL: https://api.ig.com/gateway/deal (live) / https://demo-api.ig.com/gateway/deal (demo)
  - Authentication: POST /session (v2) → CST + X-SECURITY-TOKEN headers
  - M30 resolution: "MINUTE_30"
  - SL/TP attachés nativement à l'ordre (stopLevel / limitLevel)
  - Les sessions expirent (~12h) : chaque requête re-tente une fois après re-login sur 401

Documentation: https://labs.ig.com/rest-trading-api-reference
"""
import asyncio
import logging
from typing import List

import httpx

from brokers.base_broker import BaseBroker, BrokerError

logger = logging.getLogger(__name__)

IG_LIVE_URL = "https://api.ig.com/gateway/deal"
IG_DEMO_URL = "https://demo-api.ig.com/gateway/deal"

# Attentes (s) avant chaque nouvel essai de GET /confirms après un échec.
CONFIRM_RETRY_DELAYS = (1.0, 2.0)


class IGBroker(BaseBroker):

    def __init__(self, api_key: str, identifier: str, password: str, demo: bool = True):
        self._api_key    = api_key
        self._identifier = identifier
        self._password   = password
        self._demo       = demo
        self._base_url   = IG_DEMO_URL if demo else IG_LIVE_URL
        self._cst        = ""
        self._token      = ""
        self._client     = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        return False

    def _headers(self, version: str = "2") -> dict:
        return {
            "Content-Type":     "application/json; charset=UTF-8",
            "Accept":           "application/json; charset=UTF-8",
            "X-IG-API-KEY":     self._api_key,
            "CST":              self._cst,
            "X-SECURITY-TOKEN": self._token,
            "Version":          version,
        }

    async def _request(self, method: str, path: str, *, version: str = "2",
                       params: dict = None, json_body: dict = None,
                       extra_headers: dict = None, _retried: bool = False) -> httpx.Response:
        """Requête authentifiée avec re-login automatique sur session expirée (401)."""
        headers = self._headers(version)
        if extra_headers:
            headers.update(extra_headers)
        try:
            resp = await self._client.request(
                method, f"{self._base_url}{path}",
                params=params, json=json_body, headers=headers,
            )
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401 and not _retried:
                logger.info("Session IG expirée — reconnexion")
                await self.connect()
                return await self._request(method, path, version=version, params=params,
                                           json_body=json_body, extra_headers=extra_headers,
                                           _retried=True)
            raise BrokerError(
                f"{method} {path} failed ({e.response.status_code}): {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise BrokerError(f"Network error on {method} {path}: {e}") from e

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
                f"{self._base_url}/session", json=payload, headers=headers,
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
                f"{self._base_url}/session", headers=self._headers(),
            )
        except Exception as e:
            logger.warning("IG disconnect error: %s", e)
        finally:
            await self._client.aclose()
            logger.info("Disconnected from IG Markets")

    async def get_candles(self, symbol: str, count: int, timeframe: str = "MINUTE_30",
                          start: str = "") -> List[dict]:
        """
        Sans `start` : les `count` dernières bougies.
        Avec `start` (ISO "YYYY-MM-DDTHH:MM:SS" UTC) : les bougies depuis ce timestamp.
        Attention au quota IG : 10 000 points de données / semaine sur le démo.
        """
        params = {"resolution": timeframe, "pageSize": 0}
        if start:
            params["from"] = start.replace("Z", "").split("+")[0]
        else:
            params["max"] = count
        resp = await self._request("GET", f"/prices/{symbol}", version="3", params=params)

        candles = []
        for item in resp.json().get("prices", []):
            o, h, l, c = (item.get(k) or {} for k in
                          ("openPrice", "highPrice", "lowPrice", "closePrice"))

            def mid(px):
                bid, ask = px.get("bid"), px.get("ask")
                if bid is not None and ask is not None:
                    return (bid + ask) / 2.0
                return bid if bid is not None else ask

            vals = [mid(o), mid(h), mid(l), mid(c)]
            if any(v is None for v in vals):
                continue     # bougie incomplète (marché fermé)
            candles.append({
                "time":  item["snapshotTimeUTC"],
                "open":  float(vals[0]),
                "high":  float(vals[1]),
                "low":   float(vals[2]),
                "close": float(vals[3]),
            })
        return candles

    async def get_account_info(self) -> dict:
        """
        Retourne {"balance": équity du compte, "buying_power": notionnel max ouvrable}.
        IG marge or = 5 % → buying_power ≈ fonds disponibles × 20.
        """
        resp = await self._request("GET", "/accounts", version="1")
        for acc in resp.json().get("accounts", []):
            if acc.get("preferred"):
                bal = acc.get("balance") or {}
                balance   = float(bal.get("balance") or 0.0)
                available = float(bal.get("available") or 0.0)
                return {"balance": balance, "buying_power": available * 20.0}
        return {"balance": 0.0, "buying_power": 0.0}

    async def get_account_balance(self) -> float:
        info = await self.get_account_info()
        return info["balance"]

    async def get_open_positions(self) -> List[dict]:
        try:
            resp = await self._request("GET", "/positions", version="2")
        except BrokerError as e:
            logger.warning("get_open_positions failed: %s", e)
            return []

        positions = []
        for pos in resp.json().get("positions", []):
            market   = pos.get("market", {})
            position = pos.get("position", {})
            direction = position.get("direction", "")
            bid, offer = market.get("bid"), market.get("offer")
            current = (bid if direction == "BUY" else offer) or bid or offer or 0.0
            positions.append({
                "epic":          market.get("epic", ""),
                "direction":     direction,
                "size":          float(position.get("size", 0)),
                "deal_id":       position.get("dealId", ""),
                "entry_price":   float(position.get("level", 0) or 0),
                "current_price": float(current),
                "created_at":    position.get("createdDateUTC", ""),
                "sl":            float(position.get("stopLevel") or 0),
                "tp":            float(position.get("limitLevel") or 0),
            })
        return positions

    async def open_long(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> str:
        return await self._place_order(symbol, size, "BUY", sl, tp, **kwargs)

    async def open_short(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> str:
        return await self._place_order(symbol, size, "SELL", sl, tp, **kwargs)

    async def _place_order(
        self,
        symbol:        str,
        size:          float,
        direction:     str,
        sl:            float,
        tp:            float,
        comment:       str = "",
        currency_code: str = "USD",
        **kwargs,
    ) -> str:
        payload = {
            "epic":           symbol,
            "expiry":         "-",
            "direction":      direction,
            "size":           str(round(size, 2)),
            "orderType":      "MARKET",
            "timeInForce":    "FILL_OR_KILL",
            "guaranteedStop": False,
            "forceOpen":      True,
            "stopLevel":      str(round(sl, 2)),
            "limitLevel":     str(round(tp, 2)),
            "currencyCode":   currency_code,
        }
        resp = await self._request("POST", "/positions/otc", version="2", json_body=payload)
        deal_ref = resp.json().get("dealReference", "?")
        logger.info("%s order on %s placed — dealRef: %s", direction, symbol, deal_ref)
        return await self._confirm(deal_ref, direction, symbol)

    async def _confirm(self, deal_ref: str, direction: str, symbol: str) -> str:
        """Vérifie l'acceptation du deal via /confirms. Retourne le dealId confirmé.

        IG renvoie parfois 404 (error.service.execution.find) alors que l'ordre est
        exécuté : on retente, puis on retrouve le deal dans /positions par son
        dealReference. Sans ça, main.py perd SL/TP/tier du trade (19/08, 25/09, 29/09).
        """
        resp = None
        for attempt, delay in enumerate((0,) + tuple(CONFIRM_RETRY_DELAYS), start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                resp = await self._request("GET", f"/confirms/{deal_ref}", version="1")
                break
            except BrokerError as e:
                logger.warning("Could not confirm dealRef %s (essai %d): %s",
                               deal_ref, attempt, e)
        if resp is None:
            if direction == "CLOSE":
                return ""
            return await self._find_deal_id_by_ref(deal_ref, direction, symbol)
        confirm     = resp.json()
        deal_status = confirm.get("dealStatus", "UNKNOWN")
        if deal_status != "ACCEPTED":
            reason = confirm.get("reason", "unknown reason")
            raise BrokerError(
                f"{direction} on {symbol} not accepted: {deal_status} — {reason}"
            )
        deal_id = confirm.get("dealId", "")
        logger.info("%s on %s confirmed — dealId: %s", direction, symbol, deal_id)
        return deal_id

    async def _find_deal_id_by_ref(self, deal_ref: str, direction: str, symbol: str) -> str:
        """Repli quand /confirms échoue : cherche la position ouverte portant ce dealReference."""
        try:
            resp = await self._request("GET", "/positions", version="2")
        except BrokerError as e:
            logger.warning("Repli /positions impossible pour dealRef %s: %s", deal_ref, e)
            return ""
        for pos in resp.json().get("positions", []):
            position = pos.get("position", {})
            if position.get("dealReference") == deal_ref:
                deal_id = position.get("dealId", "")
                logger.info("%s on %s retrouvé via /positions — dealId: %s",
                            direction, symbol, deal_id)
                return deal_id
        logger.warning("dealRef %s introuvable dans /positions", deal_ref)
        return ""

    async def close_position(self, symbol: str, deal_id: str = None) -> None:
        """Clôture totale au marché — cible `deal_id` si fourni, sinon la 1ère position sur `symbol`."""
        positions = await self.get_open_positions()
        if deal_id:
            pos = next((p for p in positions if p["deal_id"] == deal_id), None)
        else:
            pos = next((p for p in positions if p["epic"] == symbol), None)
        if not pos:
            logger.info("close_position %s (deal_id=%s): aucune position ouverte", symbol, deal_id)
            return
        payload = {
            "dealId":      pos["deal_id"],
            "direction":   "SELL" if pos["direction"] == "BUY" else "BUY",
            "size":        str(pos["size"]),
            "orderType":   "MARKET",
            "timeInForce": "FILL_OR_KILL",
        }
        # IG exige POST + header "_method: DELETE" pour la clôture OTC
        resp = await self._request(
            "POST", "/positions/otc", version="1",
            json_body=payload, extra_headers={"_method": "DELETE"},
        )
        deal_ref = resp.json().get("dealReference", "?")
        logger.info("Close %s (deal_id=%s) placed — dealRef: %s", symbol, pos["deal_id"], deal_ref)
        await self._confirm(deal_ref, "CLOSE", symbol)

    async def amend_stop(self, deal_id: str, new_sl: float, tp: float = None) -> None:
        """Déplace le SL d'une position déjà ouverte (breakeven) sans la fermer.

        IG's PUT /positions/otc/{dealId} peut être en sémantique "remplace" : omettre
        limitLevel risquerait d'effacer le TP existant de la position. Si `tp` est
        fourni, on le renvoie pour le préserver (voir revue finale #5c).
        """
        payload = {"stopLevel": str(round(new_sl, 2))}
        if tp is not None:
            payload["limitLevel"] = str(round(tp, 2))
        await self._request("PUT", f"/positions/otc/{deal_id}", version="2", json_body=payload)
        logger.info("SL amendé — deal_id=%s → %.2f", deal_id, new_sl)

    async def get_closed_orders_since(self, symbol: str, after_iso: str) -> List[dict]:
        """
        Transactions clôturées depuis `after_iso` (P&L réalisé par IG).
        Retourne des dicts {side, filled_avg_price, pnl} — `pnl` est le montant
        exact calculé par IG (prioritaire sur le calcul entry/exit de main.py).
        """
        from_str = after_iso.replace("Z", "").split("+")[0].split(".")[0]
        try:
            resp = await self._request(
                "GET", "/history/transactions", version="2",
                params={"type": "ALL_DEAL", "from": from_str, "pageSize": 50},
            )
        except BrokerError as e:
            logger.warning("get_closed_orders_since failed: %s", e)
            return []

        # NB : /history/transactions renvoie des DEALS COMPLETS (ouverture+clôture
        # déjà appariées par IG, avec openLevel/closeLevel/profitAndLoss), pas des
        # fills individuels façon Alpaca. "transactionType" est localisé (ex. "ORDRE"
        # sur un compte démo FR, probablement "DEAL" en EN) — filtrer sur ce libellé
        # est fragile ; `cashTransaction` (dépôts/retraits vs trades) ne l'est pas.
        results = []
        for tx in resp.json().get("transactions", []):
            if tx.get("cashTransaction", True):
                continue
            pnl_str = (tx.get("profitAndLoss") or "").strip()
            digits  = "".join(ch for ch in pnl_str if ch.isdigit() or ch in ".-")
            try:
                pnl = float(digits)
            except ValueError:
                continue
            # "size" reflète la direction du trade ORIGINAL (négatif = short/SELL,
            # positif = long/BUY) ; le "side" attendu par main.py est celui de
            # l'action de CLÔTURE, donc inversé par rapport au signe de size.
            size_str = str(tx.get("size", ""))
            closing  = "buy" if size_str.startswith("-") else "sell"
            try:
                close_level = float(tx.get("closeLevel") or 0)
            except (TypeError, ValueError):
                close_level = 0.0
            results.append({
                "side":             closing,
                "filled_avg_price": close_level,
                "pnl":              pnl,
                "instrument":       tx.get("instrumentName", ""),
            })
        return results
