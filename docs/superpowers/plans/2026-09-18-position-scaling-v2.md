# Position Scaling (3 paliers TP1/TP2/TP3 + breakeven) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le bot v2 (`donchianbot-v2`, compte démo IG `Raspi_algo02`, branche `evolve/meanrev-v2`) ouvre 3 positions par signal au lieu d'une (même entrée/SL, TP à 1×/2×/3× ATR, risque total inchangé réparti également), et remonte automatiquement le SL des positions restantes au breakeven dès que la première (TP1) est touchée.

**Architecture:** Un nouveau module pur `position_scaling.py` transforme un signal en 3 ordres dimensionnés. Le broker IG gagne deux capacités (amender un SL sans fermer la position, fermer une position précise par `deal_id`). `main.py` passe d'un suivi par actif (`_signal_cache`/`_prev_positions` indexés par `epic`) à un suivi par position individuelle (indexés par `deal_id`), avec une fonction pure d'appariement des clôtures par prix pour distinguer 3 positions du même sens sur le même actif.

**Tech Stack:** Python 3.11, httpx (async), pytest + pytest-asyncio, IG Markets REST API (démo).

**Spec:** [`docs/superpowers/specs/2026-09-18-position-scaling-v2-design.md`](../specs/2026-09-18-position-scaling-v2-design.md)

## Global Constraints

- Ce chantier ne touche que le chemin `BROKER == "ig"`. Le chemin `BROKER == "alpaca"` (legacy, inutilisé en pratique) doit rester fonctionnellement identique à aujourd'hui — changements d'interface uniquement (signatures), jamais de comportement.
- SL = 5×ATR, inchangé (ne pas toucher `MR_SL_ATR`).
- TP1 = 1×ATR, TP2 = 2×ATR, TP3 = 3×ATR — configurables via env (`MR_TP1_ATR`, `MR_TP2_ATR`, `MR_TP3_ATR`), défauts respectifs 1.0 / 2.0 / 3.0.
- Marge breakeven = 0.2×ATR côté perte (donner de l'air), configurable via env `MR_BREAKEVEN_BUFFER_ATR`, défaut 0.2.
- Chaque position risque risk_amount ÷ 3 — tailles égales entre les 3 paliers.
- `pytest tests/` doit rester intégralement vert après chaque tâche.
- Ne jamais committer de secret (`.env`, tokens, mots de passe) — aucun de ces fichiers n'est touché par ce plan.

---

### Task 1: Module `position_scaling.py` — répartition en 3 paliers

**Files:**
- Create: `app/position_scaling.py`
- Test: `tests/test_position_scaling.py`

**Interfaces:**
- Produces: `build_scaled_orders(signal: dict, risk_amount: float, contract_size: float, tp_atr_multipliers: Sequence[float] = (1.0, 2.0, 3.0)) -> List[dict]`. Chaque dict retourné a les clés : `tier` (int, 1..N), `direction` (str), `entry_price` (float), `sl_price` (float), `tp_price` (float), `qty` (float), `asset_name` (str), `symbol` (str). `signal` doit contenir `direction`, `entry_price`, `sl_price`, `atr`, `asset_name`, `symbol`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_position_scaling.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from position_scaling import build_scaled_orders

BASE_SIGNAL = {
    "direction":   "BUY",
    "entry_price": 4350.0,
    "sl_price":    4300.0,   # distance 50 == 5 x atr(10)
    "atr":         10.0,
    "asset_name":  "GOLD",
    "symbol":      "CS.D.CFEGOLD.CEF.IP",
}


def test_returns_three_orders():
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=558.69, contract_size=1.0)
    assert len(orders) == 3
    assert [o["tier"] for o in orders] == [1, 2, 3]


def test_tp_levels_are_1_2_3x_atr_for_long():
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=558.69, contract_size=1.0)
    entry, atr_val = BASE_SIGNAL["entry_price"], BASE_SIGNAL["atr"]
    assert orders[0]["tp_price"] == pytest.approx(entry + 1 * atr_val)
    assert orders[1]["tp_price"] == pytest.approx(entry + 2 * atr_val)
    assert orders[2]["tp_price"] == pytest.approx(entry + 3 * atr_val)


def test_tp_levels_go_down_for_short():
    signal = {**BASE_SIGNAL, "direction": "SELL", "sl_price": 4400.0}
    orders = build_scaled_orders(signal, risk_amount=558.69, contract_size=1.0)
    entry, atr_val = signal["entry_price"], signal["atr"]
    assert orders[0]["tp_price"] == pytest.approx(entry - 1 * atr_val)
    assert orders[2]["tp_price"] == pytest.approx(entry - 3 * atr_val)


def test_same_entry_and_sl_across_tiers():
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=558.69, contract_size=1.0)
    for o in orders:
        assert o["entry_price"] == BASE_SIGNAL["entry_price"]
        assert o["sl_price"] == BASE_SIGNAL["sl_price"]


def test_risk_split_equally_across_tiers():
    risk_amount = 558.69
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=risk_amount, contract_size=1.0)
    sl_dist = abs(BASE_SIGNAL["entry_price"] - BASE_SIGNAL["sl_price"])
    total_risked = sum(o["qty"] * sl_dist * 1.0 for o in orders)
    assert total_risked == pytest.approx(risk_amount, rel=0.1)
    assert len({o["qty"] for o in orders}) == 1   # tailles égales


def test_qty_respects_01_step_minimum():
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=1.0, contract_size=1.0)
    for o in orders:
        assert o["qty"] >= 0.1


def test_zero_sl_distance_returns_empty():
    signal = {**BASE_SIGNAL, "sl_price": BASE_SIGNAL["entry_price"]}
    assert build_scaled_orders(signal, risk_amount=500.0, contract_size=1.0) == []


def test_custom_tp_multipliers():
    orders = build_scaled_orders(
        BASE_SIGNAL, risk_amount=558.69, contract_size=1.0,
        tp_atr_multipliers=(0.5, 1.5),
    )
    assert len(orders) == 2
    entry, atr_val = BASE_SIGNAL["entry_price"], BASE_SIGNAL["atr"]
    assert orders[0]["tp_price"] == pytest.approx(entry + 0.5 * atr_val)
    assert orders[1]["tp_price"] == pytest.approx(entry + 1.5 * atr_val)


def test_asset_name_and_symbol_carried_through():
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=558.69, contract_size=1.0)
    for o in orders:
        assert o["asset_name"] == "GOLD"
        assert o["symbol"] == "CS.D.CFEGOLD.CEF.IP"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_position_scaling.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'position_scaling'`

- [ ] **Step 3: Implement `app/position_scaling.py`**

```python
"""
position_scaling.py — Split a single trading signal into N sized sub-orders
(scaled take-profits), each carrying an equal share of the total risk.
"""
from typing import Dict, List, Sequence

DEFAULT_TP_ATR_MULTIPLIERS = (1.0, 2.0, 3.0)


def build_scaled_orders(
    signal: Dict,
    risk_amount: float,
    contract_size: float,
    tp_atr_multipliers: Sequence[float] = DEFAULT_TP_ATR_MULTIPLIERS,
) -> List[Dict]:
    """
    Split `signal` (a dict as returned by analyse_meanrev(), must include "atr")
    into len(tp_atr_multipliers) sub-orders sharing the same entry/SL, each with
    its own TP at `multiplier x ATR` from entry, and an equal share of risk_amount.

    Returns a list of dicts (empty if inputs are invalid), each with keys:
      tier, direction, entry_price, sl_price, tp_price, qty, asset_name, symbol
    """
    direction = signal["direction"]
    entry     = signal["entry_price"]
    sl        = signal["sl_price"]
    atr_val   = signal["atr"]
    sign      = 1 if direction == "BUY" else -1

    sl_dist = abs(entry - sl)
    if sl_dist <= 0 or risk_amount <= 0 or not tp_atr_multipliers:
        return []

    risk_per_tier = risk_amount / len(tp_atr_multipliers)
    qty = risk_per_tier / (sl_dist * contract_size)
    qty = max(round(qty, 1), 0.1)

    orders = []
    for tier, multiplier in enumerate(tp_atr_multipliers, start=1):
        tp_price = entry + sign * multiplier * atr_val
        orders.append({
            "tier":        tier,
            "direction":   direction,
            "entry_price": entry,
            "sl_price":    sl,
            "tp_price":    round(tp_price, 2),
            "qty":         qty,
            "asset_name":  signal["asset_name"],
            "symbol":      signal["symbol"],
        })
    return orders
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_position_scaling.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add app/position_scaling.py tests/test_position_scaling.py
git commit -m "feat: add position_scaling module for TP1/TP2/TP3 order splitting"
```

---

### Task 2: ATR exposé dans le signal + constantes TP/breakeven

**Files:**
- Modify: `app/strategy_meanrev.py` (fonction `analyse_meanrev`, dict de retour)
- Modify: `app/config.py` (nouvelles constantes)
- Modify: `tests/test_strategy_meanrev.py`

**Interfaces:**
- Produces: le dict retourné par `analyse_meanrev()` gagne la clé `"atr": float` (valeur déjà calculée en interne — `atr_val`).
- Produces: `config.MR_TP1_ATR`, `config.MR_TP2_ATR`, `config.MR_TP3_ATR`, `config.MR_BREAKEVEN_BUFFER_ATR` (tous des `float`, lus depuis l'environnement, défauts 1.0 / 2.0 / 3.0 / 0.2).

- [ ] **Step 1: Write the failing test**

Ajouter dans `tests/test_strategy_meanrev.py`, après `test_tp_sl_ratio_is_tenth` :

```python
def test_signal_includes_atr():
    candles = _trending_candles_with_dip()
    sig = analyse_meanrev("GOLD", GOLD_CFG, candles, risk_amount=500.0)
    assert sig["atr"] > 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_strategy_meanrev.py::test_signal_includes_atr -v`
Expected: FAIL — `KeyError: 'atr'`

- [ ] **Step 3: Modifier `app/strategy_meanrev.py`**

Dans le dict retourné par `analyse_meanrev` (fin de la fonction), ajouter la clé `"atr"` :

```python
    return {
        "direction":   direction,
        "entry_price": entry,
        "sl_price":    round(sl_price, 2),
        "tp_price":    round(tp_price, 2),
        "qty":         qty,
        "asset_name":  asset_name,
        "symbol":      asset_config["symbol"],
        "atr":         round(atr_val, 4),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_strategy_meanrev.py -v`
Expected: PASS (toute la suite du fichier, y compris le nouveau test)

- [ ] **Step 5: Ajouter les constantes dans `app/config.py`**

Dans le bloc `# ── Strategy Mean Reversion XAUUSD v5 ─────` (après `MR_TIME_STOP`), ajouter :

```python
MR_TP1_ATR    = float(os.environ.get("MR_TP1_ATR", "1.0"))
MR_TP2_ATR    = float(os.environ.get("MR_TP2_ATR", "2.0"))
MR_TP3_ATR    = float(os.environ.get("MR_TP3_ATR", "3.0"))
MR_BREAKEVEN_BUFFER_ATR = float(os.environ.get("MR_BREAKEVEN_BUFFER_ATR", "0.2"))
```

- [ ] **Step 6: Commit**

```bash
git add app/strategy_meanrev.py app/config.py tests/test_strategy_meanrev.py
git commit -m "feat: expose ATR in signal dict, add TP tiers + breakeven buffer config"
```

---

### Task 3: Broker — `amend_stop`, `close_position` par `deal_id`, `open_long`/`open_short` renvoient le `deal_id`

**Files:**
- Modify: `app/brokers/base_broker.py`
- Modify: `app/brokers/ig_broker.py`
- Modify: `app/brokers/alpaca_broker.py`
- Test: `tests/test_brokers_interface.py` (nouveau)

**Interfaces:**
- Produces: `BaseBroker.open_long(...) -> str` et `open_short(...) -> str` (identifiant de position, `deal_id` pour IG / `order_id` pour Alpaca — chaîne vide si le broker ne peut pas le déterminer).
- Produces: `BaseBroker.close_position(symbol: str, deal_id: str = None) -> None` — si `deal_id` fourni, cible cette position précise.
- Produces: `BaseBroker.amend_stop(deal_id: str, new_sl: float) -> None` — nouvelle méthode abstraite.

- [ ] **Step 1: Modifier `app/brokers/base_broker.py`**

Remplacer les méthodes `open_long`, `open_short`, `close_position` et ajouter `amend_stop` :

```python
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
```

- [ ] **Step 2: Modifier `app/brokers/ig_broker.py`**

Remplacer `open_long`/`open_short`/`_place_order`/`_confirm`/`close_position` par :

```python
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
        """Vérifie l'acceptation du deal via /confirms. Retourne le dealId confirmé."""
        try:
            resp = await self._request("GET", f"/confirms/{deal_ref}", version="1")
        except BrokerError as e:
            logger.warning("Could not confirm dealRef %s: %s", deal_ref, e)
            return ""
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

    async def amend_stop(self, deal_id: str, new_sl: float) -> None:
        """Déplace le SL d'une position déjà ouverte (breakeven) sans la fermer."""
        payload = {"stopLevel": str(round(new_sl, 2))}
        await self._request("PUT", f"/positions/otc/{deal_id}", version="2", json_body=payload)
        logger.info("SL amendé — deal_id=%s → %.2f", deal_id, new_sl)
```

Note : `_confirm` est aussi appelée par `close_position` (avec `direction="CLOSE"`) — son retour (`str`) y est ignoré, ce qui reste valide en Python.

- [ ] **Step 3: Modifier `app/brokers/alpaca_broker.py`**

Modifier `open_long`/`open_short`/`close_position`, ajouter `amend_stop` :

```python
    async def open_long(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> str:
        return await self._place_order(symbol, size, "buy", sl, tp)

    async def open_short(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> str:
        return await self._place_order(symbol, size, "sell", sl, tp)

    async def close_position(self, symbol: str, deal_id: str = None) -> None:
        """
        Liquidate the entire open position for a symbol at market price.
        `deal_id` is accepted for interface compatibility but unused — Alpaca's
        DELETE /v2/positions/{symbol} always liquidates the whole position on
        that symbol (this project never opens more than one Alpaca position
        per symbol).
        """
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

    async def amend_stop(self, deal_id: str, new_sl: float) -> None:
        raise BrokerError(
            "amend_stop non supporté par AlpacaBroker — non utilisé par la stratégie legacy"
        )
```

Et dans `_place_order`, les deux branches (`crypto` et `stock`) doivent `return order_id` à la fin au lieu de `return` (nu) / rien :
- Branche crypto : remplacer le `return` final (après le `logger.info(...)`) par `return order_id`.
- Branche stock : ajouter `return order_id` après le `logger.info(...)` final de la fonction.

- [ ] **Step 4: Write the interface smoke test**

Create `tests/test_brokers_interface.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from brokers.ig_broker import IGBroker
from brokers.alpaca_broker import AlpacaBroker


def test_ig_broker_implements_full_interface():
    # Échoue à l'instanciation (TypeError) si une méthode abstraite manque.
    broker = IGBroker("key", "id", "pwd", demo=True)
    assert hasattr(broker, "amend_stop")
    assert hasattr(broker, "close_position")


def test_alpaca_broker_implements_full_interface():
    broker = AlpacaBroker("key", "secret", demo=True)
    assert hasattr(broker, "amend_stop")
    assert hasattr(broker, "close_position")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_brokers_interface.py -v`
Expected: PASS (2 tests). Si `TypeError: Can't instantiate abstract class ... with abstract method amend_stop` apparaît, une des deux implémentations broker a été oubliée — revenir au Step 2 ou 3.

- [ ] **Step 6: Run full suite to check no regression**

Run: `pytest tests/ -v`
Expected: PASS (toute la suite, y compris les tests déjà existants qui n'appellent pas directement le broker)

- [ ] **Step 7: Commit**

```bash
git add app/brokers/base_broker.py app/brokers/ig_broker.py app/brokers/alpaca_broker.py tests/test_brokers_interface.py
git commit -m "feat: broker interface gains amend_stop + deal_id-aware close_position"
```

---

### Task 4: Fonction pure d'appariement des clôtures (`_match_closed_deal`)

**Files:**
- Modify: `app/main.py` (nouvelle fonction module-level)
- Test: `tests/test_closed_deal_matching.py` (nouveau)

**Interfaces:**
- Consumes: rien de nouveau (fonction pure, aucune dépendance broker).
- Produces: `_match_closed_deal(direction: str, cache_entry: dict, candidates: List[dict]) -> Optional[dict]`. `cache_entry` a au moins les clés `tp`, `sl` (float). `candidates` est une liste de dicts au format retourné par `get_closed_orders_since()` (clés `side`, `filled_avg_price`, et éventuellement `pnl`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_closed_deal_matching.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import main as m

LONG_CACHE = {"direction": "BUY", "tp": 4360.0, "sl": 4300.0, "tier": 1}


def test_matches_transaction_closest_to_tp():
    candidates = [
        {"side": "sell", "filled_avg_price": 4300.5, "pnl": -50.0},  # proche du SL
        {"side": "sell", "filled_avg_price": 4359.8, "pnl": 10.0},   # proche du TP
    ]
    match = m._match_closed_deal("BUY", LONG_CACHE, candidates)
    assert match["filled_avg_price"] == 4359.8


def test_ignores_wrong_closing_side():
    candidates = [
        {"side": "buy", "filled_avg_price": 4359.8, "pnl": 10.0},   # mauvais camp (ouverture, pas clôture)
    ]
    assert m._match_closed_deal("BUY", LONG_CACHE, candidates) is None


def test_no_candidates_returns_none():
    assert m._match_closed_deal("BUY", LONG_CACHE, []) is None


def test_short_direction_closing_side_is_buy():
    cache = {"direction": "SELL", "tp": 4300.0, "sl": 4360.0, "tier": 1}
    candidates = [{"side": "buy", "filled_avg_price": 4300.2, "pnl": 20.0}]
    match = m._match_closed_deal("SELL", cache, candidates)
    assert match is not None


def test_degenerate_case_two_deals_same_sl_still_matches_one():
    # Positions 2 et 3 fermées ensemble sur le même SL : les deux candidats sont
    # équidistants du SL, la fonction doit renvoyer l'un des deux sans erreur.
    cache_tier2 = {"direction": "BUY", "tp": 4370.0, "sl": 4300.0, "tier": 2}
    candidates = [
        {"side": "sell", "filled_avg_price": 4300.0, "pnl": -186.0},
        {"side": "sell", "filled_avg_price": 4300.0, "pnl": -186.0},
    ]
    match = m._match_closed_deal("BUY", cache_tier2, candidates)
    assert match is not None
    assert match["filled_avg_price"] == 4300.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_closed_deal_matching.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute '_match_closed_deal'`

- [ ] **Step 3: Ajouter `_match_closed_deal` dans `app/main.py`**

Ajouter cette fonction module-level, juste après la définition de `_prev_positions`/`_last_cycle_iso` (avant `handle_telegram_command`) :

```python
def _match_closed_deal(direction: str, cache_entry: dict, candidates: list) -> dict | None:
    """
    Trouve, parmi `candidates` (sortie de get_closed_orders_since), la transaction
    qui correspond le mieux à une position disparue de get_open_positions(), en
    comparant le prix de clôture au TP/SL mis en cache pour CE deal_id précis.

    Chaque palier (tier) a un TP distinct, donc identification fiable pour repérer
    lequel a touché son TP. Cas dégénéré accepté : si 2 positions se ferment ensemble
    sur le même SL, la fonction retourne l'une des deux candidates équidistantes —
    sans impact financier réel puisqu'elles partagent taille/entry/SL (voir spec).
    """
    closing_side = "sell" if direction == "BUY" else "buy"
    same_side = [c for c in candidates if c["side"] == closing_side]
    if not same_side:
        return None

    tp, sl = cache_entry.get("tp", 0.0), cache_entry.get("sl", 0.0)

    def distance(c: dict) -> float:
        level = c["filled_avg_price"]
        refs = [abs(level - ref) for ref in (tp, sl) if ref]
        return min(refs) if refs else float("inf")

    return min(same_side, key=distance)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_closed_deal_matching.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_closed_deal_matching.py
git commit -m "feat: add price-based closed-deal matching for multi-position epics"
```

---

### Task 5: `main.py` — suivi par `deal_id` + ouverture des 3 positions (chemin IG)

**Files:**
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `build_scaled_orders` (Task 1), `config.MR_TP1_ATR/MR_TP2_ATR/MR_TP3_ATR` (Task 2), `broker.open_long/open_short -> str` (Task 3).
- Produces: `_signal_cache` désormais indexé par `deal_id` (clés par entrée : `epic`, `asset_name`, `direction`, `tier`, `entry`, `sl`, `tp`, `atr`, `qty`, `opened_at`). `_prev_positions` désormais indexé par `deal_id` (clés : `epic`, `direction`, `entry_price`, `qty`).

Ce chantier ne touche pas la logique de détection du signal ni le plafonnement de notionnel (appliqués une fois, avant la répartition en 3 paliers, exactement comme aujourd'hui sur le signal complet).

- [ ] **Step 1: Import `build_scaled_orders` et les nouvelles constantes de config**

Dans `app/main.py`, ajouter à l'import existant depuis `config` :

```python
from config import (
    BROKER, ALPACA_API_KEY, ALPACA_API_SECRET, DEMO_MODE,
    IG_API_KEY, IG_IDENTIFIER, IG_PASSWORD,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    RISK_PCT, DONCHIAN_LENGTH, LOOKBACK_CANDLES,
    POINT_VALUE, RR_RATIO,
    MR_BB_LEN, MR_BB_STD, MR_RSI_LEN, MR_RSI_LO, MR_EMA_LEN, MR_ATR_LEN,
    MR_TP_ATR, MR_SL_ATR, MR_TIME_STOP, MR_SESS_START, MR_SESS_END,
    MR_TP1_ATR, MR_TP2_ATR, MR_TP3_ATR, MR_BREAKEVEN_BUFFER_ATR,
    LOG_FILE, LOG_LEVEL, DATA_DIR,
)
```

Et ajouter l'import du nouveau module, juste après `from strategy_meanrev import analyse_meanrev` :

```python
from position_scaling import build_scaled_orders
```

- [ ] **Step 2: Remplacer le bloc "Place the order" dans `run_cycle()`**

Repérer le bloc actuel (fin de la boucle `for asset_name, asset_config in ENABLED_ASSETS.items():`, section `# Place the order`, qui va de `try:` (juste après le check de pause) jusqu'au `except BrokerError as e:` correspondant, avant le `except Exception as e:` englobant). Le remplacer intégralement par :

```python
            # Place the order(s)
            if BROKER == "ig":
                orders = build_scaled_orders(
                    signal, risk_amount, contract_size,
                    tp_atr_multipliers=(MR_TP1_ATR, MR_TP2_ATR, MR_TP3_ATR),
                )
                any_failed = False
                for order in orders:
                    try:
                        if order["direction"] == "BUY":
                            deal_id = await broker.open_long(
                                epic, order["qty"], order["sl_price"], order["tp_price"],
                                comment=f"ZorionBot_{asset_name}_T{order['tier']}",
                                currency_code=asset_config.get("currency_code", "EUR"),
                            )
                        else:
                            deal_id = await broker.open_short(
                                epic, order["qty"], order["sl_price"], order["tp_price"],
                                comment=f"ZorionBot_{asset_name}_T{order['tier']}",
                                currency_code=asset_config.get("currency_code", "EUR"),
                            )
                        if not deal_id:
                            raise BrokerError(
                                f"Aucun deal_id retourné pour le palier {order['tier']}"
                            )

                        signals_found += 1
                        _signal_cache[deal_id] = {
                            "epic":       epic,
                            "asset_name": asset_name,
                            "direction":  order["direction"],
                            "tier":       order["tier"],
                            "entry":      order["entry_price"],
                            "sl":         order["sl_price"],
                            "tp":         order["tp_price"],
                            "atr":        signal["atr"],
                            "qty":        order["qty"],
                            "opened_at":  now.isoformat(),
                        }
                        _prev_positions[deal_id] = {
                            "epic":        epic,
                            "direction":   order["direction"],
                            "entry_price": order["entry_price"],
                            "qty":         order["qty"],
                        }
                        await telegram.send_signal(order, DEMO_MODE)

                    except BrokerError as e:
                        any_failed = True
                        logger.error("BrokerError %s tier %d: %s", asset_name, order["tier"], e)
                        await telegram.send_error(f"Order {asset_name} tier {order['tier']}", str(e))

                if orders:
                    _save_state({"open_signal_cache": _signal_cache})
                if any_failed:
                    _order_failure_cooldown[epic] = now.isoformat()

            else:
                # Chemin Alpaca (legacy) — comportement inchangé, une seule position.
                try:
                    if signal["direction"] == "BUY":
                        await broker.open_long(
                            epic, signal["qty"], signal["sl_price"], signal["tp_price"],
                            comment=f"ZorionBot_{asset_name}",
                            currency_code=asset_config.get("currency_code", "EUR"),
                        )
                    else:
                        await broker.open_short(
                            epic, signal["qty"], signal["sl_price"], signal["tp_price"],
                            comment=f"ZorionBot_{asset_name}",
                            currency_code=asset_config.get("currency_code", "EUR"),
                        )
                    signals_found += 1
                    _signal_cache[epic] = {
                        "sl":         signal["sl_price"],
                        "tp":         signal["tp_price"],
                        "qty":        signal["qty"],
                        "entry":      signal["entry_price"],
                        "asset_name": asset_name,
                        "direction":  signal["direction"],
                        "opened_at":  now.isoformat(),
                    }
                    _save_state({"open_signal_cache": _signal_cache})
                    _prev_positions[epic] = {
                        "direction":   signal["direction"],
                        "entry_price": signal["entry_price"],
                        "qty":         signal["qty"],
                    }
                    await telegram.send_signal(signal, DEMO_MODE)

                except BrokerError as e:
                    logger.error("BrokerError %s: %s", asset_name, e)
                    _order_failure_cooldown[epic] = now.isoformat()
                    await telegram.send_error(
                        f"Order {asset_name}",
                        f"{e}\n⏸ Pas de nouvelle tentative pendant {_ORDER_FAILURE_COOLDOWN_MINUTES} min.",
                    )
```

Politique d'échec partiel (chemin IG) : si le palier 1 s'ouvre mais que le palier 2 échoue, le palier 1 reste ouvert et suivi normalement — pas de rollback. L'échec est notifié via Telegram et déclenche le cooldown de l'actif (comme aujourd'hui pour un échec simple), pour éviter un nouveau essai immédiat au cycle suivant.

- [ ] **Step 3: Run full suite**

Run: `pytest tests/ -v`
Expected: PASS. Ce changement n'a pas de test dédié (pas de harnais d'intégration pour `run_cycle()` dans ce projet — convention existante) ; la vérification se fait par relecture + par la suite complète qui doit rester verte, et sera complétée par le smoke test de déploiement en Task 9.

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: open 3 scaled positions per signal on IG path, track by deal_id"
```

---

### Task 6: Tags de palier dans Telegram (`/status`, signal, clôture, `/trades`)

**Files:**
- Modify: `app/telegram_notifier.py`
- Modify: `app/main.py` (points d'appel `/status`)
- Modify: `tests/test_telegram_notifier.py`

**Interfaces:**
- Produces: `send_signal(signal: dict, demo: bool)` affiche `Position N/3` si `signal.get("tier")` est présent.
- Produces: `send_trade_closed(symbol, direction, pnl, demo, tier: int = 0)` (nouveau paramètre optionnel) — utilisé par la Task 7.
- Produces: `_format_open_position(idx, pos, cache_entry)` affiche `(Position N/3)` si `cache_entry.get("tier")` est présent ; les appelants doivent chercher `cache_entry` par `pos["deal_id"]` (disponible depuis la Task 5, plus par `pos["epic"]`).

- [ ] **Step 1: Write the failing tests**

Ajouter dans `tests/test_telegram_notifier.py` (dans la classe/section correspondant à `_format_open_position` et `send_signal` — suivre le style des tests existants du fichier) :

```python
def test_format_open_position_shows_tier_tag():
    from telegram_notifier import _format_open_position
    pos = {"epic": "CS.D.CFEGOLD.CEF.IP", "direction": "BUY",
           "entry_price": 4350.0, "current_price": 4355.0, "unrealized_pl": 5.0}
    cache_entry = {"sl": 4300.0, "tp": 4360.0, "tier": 2}
    text = _format_open_position(1, pos, cache_entry)
    assert "Position 2/3" in text


def test_format_open_position_no_tag_without_tier():
    from telegram_notifier import _format_open_position
    pos = {"epic": "SPY", "direction": "BUY",
           "entry_price": 500.0, "current_price": 501.0, "unrealized_pl": 1.0}
    cache_entry = {"sl": 495.0, "tp": 510.0}   # pas de "tier" (chemin Alpaca legacy)
    text = _format_open_position(1, pos, cache_entry)
    assert "Position" not in text.split("SL")[0].split("\n")[0] or "/3" not in text
```

- [ ] **Step 2: Run tests to verify the first one fails**

Run: `pytest tests/test_telegram_notifier.py -v`
Expected: `test_format_open_position_shows_tier_tag` FAIL (pas de tag affiché) ; `test_format_open_position_no_tag_without_tier` PASS déjà (rien à faire sans tier).

- [ ] **Step 3: Modifier `_format_open_position` dans `app/telegram_notifier.py`**

Remplacer la ligne de construction de `lines` (début de la fonction) :

```python
    direction = "🚀 LONG" if pos["direction"] == "BUY" else "🔻 SHORT"
    pnl       = pos.get("unrealized_pl", 0.0)
    pnl_str   = f"{'+'if pnl > 0 else ''}{pnl:.2f} $"
    entry     = pos.get("entry_price", 0.0)
    current   = pos.get("current_price", 0.0)

    lines = [
        f"<b>#{idx} {direction} {pos['epic']}</b>",
        f"   Entrée  : {entry:.2f} → Actuel : {current:.2f}",
        f"   P&amp;L  : {pnl_str}",
    ]
```

par :

```python
    direction = "🚀 LONG" if pos["direction"] == "BUY" else "🔻 SHORT"
    pnl       = pos.get("unrealized_pl", 0.0)
    pnl_str   = f"{'+'if pnl > 0 else ''}{pnl:.2f} $"
    entry     = pos.get("entry_price", 0.0)
    current   = pos.get("current_price", 0.0)
    tier      = cache_entry.get("tier") if cache_entry else None
    tier_str  = f" (Position {tier}/3)" if tier else ""

    lines = [
        f"<b>#{idx} {direction} {pos['epic']}{tier_str}</b>",
        f"   Entrée  : {entry:.2f} → Actuel : {current:.2f}",
        f"   P&amp;L  : {pnl_str}",
    ]
```

- [ ] **Step 4: Modifier `send_signal`**

Remplacer :

```python
    async def send_signal(self, signal: dict, demo: bool) -> None:
        direction = "🚀 LONG" if signal["direction"] == "BUY" else "🔻 SHORT"
        mode_tag  = "[DEMO] " if demo else ""
        await self._send(
            f"{direction} {mode_tag}<b>{signal['asset_name']}</b>\n"
            f"Entry : {signal['entry_price']:.2f}\n"
            f"SL    : {signal['sl_price']:.2f}\n"
            f"TP    : {signal['tp_price']:.2f}\n"
            f"Qté   : {signal['qty']:.4f}"
        )
```

par :

```python
    async def send_signal(self, signal: dict, demo: bool) -> None:
        direction = "🚀 LONG" if signal["direction"] == "BUY" else "🔻 SHORT"
        mode_tag  = "[DEMO] " if demo else ""
        tier      = signal.get("tier")
        tier_str  = f" — Position {tier}/3" if tier else ""
        await self._send(
            f"{direction} {mode_tag}<b>{signal['asset_name']}</b>{tier_str}\n"
            f"Entry : {signal['entry_price']:.2f}\n"
            f"SL    : {signal['sl_price']:.2f}\n"
            f"TP    : {signal['tp_price']:.2f}\n"
            f"Qté   : {signal['qty']:.4f}"
        )
```

- [ ] **Step 5: Modifier `send_trade_closed`**

Remplacer :

```python
    async def send_trade_closed(
        self, symbol: str, direction: str, pnl: float, demo: bool
    ) -> None:
        emoji         = "💰" if pnl >= 0 else "💸"
        result        = "WIN ✅" if pnl >= 0 else "LOSS ❌"
        direction_str = "LONG" if direction == "BUY" else "SHORT"
        mode_tag      = "[DEMO] " if demo else ""
        pnl_str       = f"{'+'if pnl >= 0 else ''}{pnl:.2f} $"
        await self._send(
            f"{emoji} <b>Trade fermé {mode_tag}{symbol}</b>\n"
            f"Direction : {direction_str}\n"
            f"P&amp;L    : {pnl_str}\n"
            f"Résultat  : <b>{result}</b>"
        )
```

par :

```python
    async def send_trade_closed(
        self, symbol: str, direction: str, pnl: float, demo: bool, tier: int = 0
    ) -> None:
        emoji         = "💰" if pnl >= 0 else "💸"
        result        = "WIN ✅" if pnl >= 0 else "LOSS ❌"
        direction_str = "LONG" if direction == "BUY" else "SHORT"
        mode_tag      = "[DEMO] " if demo else ""
        pnl_str       = f"{'+'if pnl >= 0 else ''}{pnl:.2f} $"
        tier_str      = f" — Position {tier}/3" if tier else ""
        await self._send(
            f"{emoji} <b>Trade fermé {mode_tag}{symbol}</b>{tier_str}\n"
            f"Direction : {direction_str}\n"
            f"P&amp;L    : {pnl_str}\n"
            f"Résultat  : <b>{result}</b>"
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_telegram_notifier.py -v`
Expected: PASS (toute la suite du fichier)

- [ ] **Step 7: Mettre à jour les points d'appel dans `app/main.py`**

Dans `handle_telegram_command`, cas `/status` — remplacer :

```python
                for idx, p in enumerate(positions, 1):
                    cache_entry = _signal_cache.get(p["epic"])
                    lines.append(_format_open_position(idx, p, cache_entry))
```

par :

```python
                for idx, p in enumerate(positions, 1):
                    cache_entry = _signal_cache.get(p["deal_id"])
                    lines.append(_format_open_position(idx, p, cache_entry))
```

Dans `app/telegram_notifier.py`, `send_daily_summary` — remplacer :

```python
        if open_positions:
            lines.append(f"\n<b>Positions ouvertes ({len(open_positions)}) :</b>")
            for idx, pos in enumerate(open_positions, 1):
                cache_entry = signal_cache.get(pos["epic"])
                lines.append(_format_open_position(idx, pos, cache_entry))
```

par :

```python
        if open_positions:
            lines.append(f"\n<b>Positions ouvertes ({len(open_positions)}) :</b>")
            for idx, pos in enumerate(open_positions, 1):
                cache_entry = signal_cache.get(pos["deal_id"])
                lines.append(_format_open_position(idx, pos, cache_entry))
```

Dans `app/main.py`, cas `/trades` de `handle_telegram_command` — remplacer la ligne de formatage d'un trade :

```python
            for t in trades:
                emoji  = "✅" if t["pnl"] >= 0 else "❌"
                d_str  = "LONG " if t["direction"] == "BUY" else "SHORT"
                pnl_s  = f"{'+'if t['pnl'] > 0 else ''}{t['pnl']:.2f} $"
                date_s = t["closed_at"][8:10] + "/" + t["closed_at"][5:7] + " " + t["closed_at"][11:16]
                lines.append(f"#{t['id']} {emoji} {d_str} {t['symbol']} | {pnl_s} | {date_s}")
```

par :

```python
            for t in trades:
                emoji     = "✅" if t["pnl"] >= 0 else "❌"
                d_str     = "LONG " if t["direction"] == "BUY" else "SHORT"
                pnl_s     = f"{'+'if t['pnl'] > 0 else ''}{t['pnl']:.2f} $"
                date_s    = t["closed_at"][8:10] + "/" + t["closed_at"][5:7] + " " + t["closed_at"][11:16]
                tier_tag  = f" T{t['tier']}" if t.get("tier") else ""
                lines.append(f"#{t['id']} {emoji} {d_str} {t['symbol']}{tier_tag} | {pnl_s} | {date_s}")
```

- [ ] **Step 8: Run full suite**

Run: `pytest tests/ -v`
Expected: PASS (suite complète)

- [ ] **Step 9: Commit**

```bash
git add app/telegram_notifier.py app/main.py tests/test_telegram_notifier.py
git commit -m "feat: tag Telegram messages and /trades with tier (1/3, 2/3, 3/3)"
```

---

### Task 7: `main.py` — détection de clôture par `deal_id`, journal avec `tier`, déclenchement breakeven

**Files:**
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `_match_closed_deal` (Task 4), `broker.amend_stop` (Task 3).
- Produces: `_add_to_journal(..., tier: int = 0) -> int` (signature étendue, rétrocompatible) ; nouvelle fonction `_apply_breakeven(broker, telegram, epic, closed_deal_id, cache_entry) -> None`.

- [ ] **Step 1: Étendre `_add_to_journal` avec le champ `tier`**

Remplacer la fonction `_add_to_journal` existante par :

```python
def _add_to_journal(
    journal: dict,
    symbol: str,
    asset_name: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    sl_price: float,
    tp_price: float,
    qty: float,
    pnl: float,
    closed_at: str,
    tier: int = 0,
) -> int:
    """Ajoute un trade clôturé au journal. Retourne l'ID assigné."""
    trade_id = journal["next_id"]
    journal["trades"].append({
        "id":          trade_id,
        "symbol":      symbol,
        "asset_name":  asset_name,
        "tier":        tier,
        "direction":   direction,
        "entry_price": round(entry_price, 4),
        "exit_price":  round(exit_price, 4),
        "sl_price":    round(sl_price, 4),
        "tp_price":    round(tp_price, 4),
        "qty":         round(qty, 6),
        "pnl":         round(pnl, 2),
        "closed_at":   closed_at,
    })
    journal["next_id"] = trade_id + 1
    return trade_id
```

- [ ] **Step 2: Write the failing test for the tier field**

Ajouter dans `tests/test_journal.py`, dans `TestJournalAddTrade` :

```python
    def test_trade_stores_tier(self, tmp_path):
        import main as m
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        journal = {"month": "2026-04", "next_id": 1, "trades": []}

        m._add_to_journal(
            journal, symbol="CS.D.CFEGOLD.CEF.IP", asset_name="GOLD", direction="BUY",
            entry_price=4350.0, exit_price=4360.0, sl_price=4300.0, tp_price=4360.0,
            qty=0.4, pnl=4.0, closed_at="2026-09-18T10:00:00Z", tier=1,
        )

        assert journal["trades"][0]["tier"] == 1
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_journal.py -v`
Expected: PASS (le test passe directement, la fonction a été étendue au Step 1 ; ce test verrouille le comportement pour la suite).

- [ ] **Step 4: Ajouter `_apply_breakeven` dans `app/main.py`**

Ajouter cette fonction juste après `_match_closed_deal` :

```python
async def _apply_breakeven(
    broker: IGBroker,
    telegram: TelegramNotifier,
    epic: str,
    closed_deal_id: str,
    cache_entry: dict,
) -> None:
    """TP1 touché : remonte le SL des positions sœurs (même epic) encore ouvertes."""
    direction = cache_entry.get("direction", "BUY")
    entry     = cache_entry.get("entry", 0.0)
    atr_val   = cache_entry.get("atr", 0.0)
    sign      = 1 if direction == "BUY" else -1
    new_sl    = entry - sign * MR_BREAKEVEN_BUFFER_ATR * atr_val

    siblings = [
        (deal_id, entry_data) for deal_id, entry_data in _signal_cache.items()
        if entry_data.get("epic") == epic and deal_id != closed_deal_id
    ]
    if not siblings:
        return

    amended = False
    for deal_id, entry_data in siblings:
        try:
            await broker.amend_stop(deal_id, new_sl)
            entry_data["sl"] = new_sl
            amended = True
            logger.info(
                "Breakeven appliqué — deal_id=%s (tier %s) → SL=%.2f",
                deal_id, entry_data.get("tier"), new_sl,
            )
        except BrokerError as e:
            logger.error("Échec amend_stop breakeven deal_id=%s: %s", deal_id, e)
            await telegram.send_error(f"Breakeven {epic}", str(e))

    if amended:
        _save_state({"open_signal_cache": _signal_cache})
        await telegram._send(
            f"🔒 <b>{epic}</b> — TP1 touché, SL des positions restantes remonté "
            f"au breakeven ({new_sl:.2f})"
        )
```

Note : `IGBroker` doit être importé dans `main.py` pour l'annotation de type (déjà importé aujourd'hui via `from brokers.ig_broker import IGBroker`, aucun changement d'import requis ici).

- [ ] **Step 5: Remplacer le bloc "Detect closed positions" dans `run_cycle()`**

Repérer le bloc actuel (commentaire `# ── Detect closed positions ───`, qui itère sur `_prev_positions.items()` par `symbol`) jusqu'à la mise à jour de `_prev_positions` juste avant `signals_found = 0`. Le remplacer intégralement par :

```python
    # ── Detect closed positions (par deal_id — plusieurs positions possibles par epic) ──
    current_deal_ids = {p["deal_id"] for p in open_positions}
    missing = [
        (deal_id, pos_data) for deal_id, pos_data in _prev_positions.items()
        if deal_id not in current_deal_ids
    ]

    if missing and _last_cycle_iso:
        epics_to_check = {pos_data["epic"] for _, pos_data in missing}
        closed_by_epic = {
            epic: await broker.get_closed_orders_since(epic, _last_cycle_iso)
            for epic in epics_to_check
        }

        # Tier 1 en premier : son TP est le plus facile à distinguer sans ambiguïté.
        missing.sort(key=lambda item: _signal_cache.get(item[0], {}).get("tier", 99))

        for deal_id, pos_data in missing:
            epic         = pos_data["epic"]
            cache_entry  = _signal_cache.get(deal_id, {})
            candidates   = closed_by_epic.get(epic, [])
            match        = _match_closed_deal(pos_data["direction"], cache_entry, candidates)

            if match is None:
                logger.warning(
                    "Impossible d'apparier la clôture de %s (deal_id=%s) — ignoré ce cycle",
                    epic, deal_id,
                )
                continue
            candidates.remove(match)   # ne pas réutiliser la même transaction

            try:
                exit_price  = match["filled_avg_price"]
                entry_price = pos_data["entry_price"]
                qty         = pos_data["qty"]
                if match.get("pnl") is not None:
                    pnl = match["pnl"]
                elif pos_data["direction"] == "BUY":
                    pnl = (exit_price - entry_price) * qty
                else:
                    pnl = (entry_price - exit_price) * qty

                tier = cache_entry.get("tier", 0)
                logger.info(
                    "Trade closed — %s %s (tier %s) | entry=%.2f exit=%.2f P&L=%.2f",
                    pos_data["direction"], epic, tier, entry_price, exit_price, pnl,
                )
                await telegram.send_trade_closed(epic, pos_data["direction"], pnl, DEMO_MODE, tier=tier)

                _add_to_journal(
                    _journal,
                    symbol      = epic,
                    asset_name  = cache_entry.get("asset_name", epic),
                    direction   = pos_data["direction"],
                    entry_price = entry_price,
                    exit_price  = exit_price,
                    sl_price    = cache_entry.get("sl", 0.0),
                    tp_price    = cache_entry.get("tp", 0.0),
                    qty         = qty,
                    pnl         = pnl,
                    closed_at   = now.isoformat(),
                    tier        = tier,
                )
                _save_journal(_journal)

                # ── Bascule breakeven : tier 1 fermé en profit ──
                if pnl > 0 and tier == 1:
                    await _apply_breakeven(broker, telegram, epic, deal_id, cache_entry)

                _signal_cache.pop(deal_id, None)
                _save_state({"open_signal_cache": _signal_cache})
            except Exception as e:
                logger.warning("Could not process closed trade for %s (deal_id=%s): %s", epic, deal_id, e)

    # Update position tracking for next cycle
    _prev_positions = {
        p["deal_id"]: {
            "epic":        p["epic"],
            "direction":   p["direction"],
            "entry_price": p.get("entry_price", 0),
            "qty":         p["size"],
        }
        for p in open_positions
    }
    _last_cycle_iso = now.isoformat()
```

- [ ] **Step 6: Run full suite**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/test_journal.py
git commit -m "feat: match closures by deal_id/price, tag journal with tier, trigger breakeven"
```

---

### Task 8: `main.py` — monitoring TP/SL manuel et time stop ciblent un `deal_id`

**Files:**
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `_signal_cache` désormais indexé par `deal_id` pour le chemin IG, toujours par `epic` pour le chemin Alpaca legacy (Task 5 + le correctif de la Task 7), `broker.close_position(symbol, deal_id=...)` (Task 3).

> **Piège déjà rencontré à la Task 7, à ne pas reproduire ici :** le bloc visé par le Step 1 (`# ── TP/SL monitoring (tous actifs) ───`) n'est **pas** filtré par `if BROKER == "ig":` — il s'applique à **toutes** les positions ouvertes, IG et Alpaca confondues (le commentaire "tous actifs" est littéral). Pour Alpaca, c'est même l'unique mécanisme qui fait respecter le TP/SL (Alpaca n'attache pas de stop natif, contrairement à IG). `_signal_cache` reste indexé par `epic` pour Alpaca (jamais migré vers `deal_id`) — un remplacement inconditionnel de la clé de lookup casserait silencieusement le TP/SL manuel d'Alpaca exactement comme le bug déjà corrigé à la Task 7. Le Step 1 ci-dessous branche donc explicitly par `BROKER`, contrairement au Step 2 dont le bloc est déjà nativement sous un `if BROKER == "ig":` englobant (donc sûr sans branchement supplémentaire).

- [ ] **Step 1: Mettre à jour la boucle de monitoring TP/SL manuel**

Repérer le bloc `# ── TP/SL monitoring (tous actifs) ───` dans `run_cycle()`. Remplacer les deux lignes :

```python
    for pos in open_positions:
        epic = pos["epic"]
        cache = _signal_cache.get(epic)
```

par :

```python
    for pos in open_positions:
        epic      = pos["epic"]
        deal_id   = pos["deal_id"]
        cache_key = deal_id if BROKER == "ig" else epic
        cache     = _signal_cache.get(cache_key)
```

Et plus loin dans le même bloc, remplacer :

```python
            try:
                await broker.close_position(epic)
```

par :

```python
            try:
                if BROKER == "ig":
                    await broker.close_position(epic, deal_id=deal_id)
                else:
                    await broker.close_position(epic)
```

- [ ] **Step 2: Mettre à jour la boucle de time stop**

Repérer le bloc `# ── Time stop (mean reversion) ───` (`if BROKER == "ig":`). Remplacer :

```python
        for pos in open_positions:
            epic  = pos["epic"]
            cache = _signal_cache.get(epic)
```

par :

```python
        for pos in open_positions:
            epic    = pos["epic"]
            deal_id = pos["deal_id"]
            cache   = _signal_cache.get(deal_id)
```

Et plus loin dans le même bloc, remplacer :

```python
                try:
                    await broker.close_position(epic)
```

par :

```python
                try:
                    await broker.close_position(epic, deal_id=deal_id)
```

- [ ] **Step 3: Run full suite**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "fix: target deal_id in TP/SL monitoring and time-stop closes"
```

---

### Task 9: Régression complète, déploiement sur `donchianbot-v2`, vérification en direct

**Files:** aucun (validation + déploiement)

- [ ] **Step 1: Suite complète locale**

Run: `pytest tests/ -v`
Expected: PASS intégral (toutes les tâches précédentes + suite historique).

- [ ] **Step 2: Revue à froid contre la spec**

Relire [`docs/superpowers/specs/2026-09-18-position-scaling-v2-design.md`](../specs/2026-09-18-position-scaling-v2-design.md) section par section et vérifier que chaque point a une tâche correspondante déjà exécutée (répartition égale, TP1/2/3, breakeven avec marge 0.2×ATR, tags Telegram, journal). Aucun changement de code attendu à cette étape — uniquement une checklist de couverture.

- [ ] **Step 3: Déployer sur le Pi (`donchianbot-v2`)**

Empaqueter et transférer le worktree comme pour le déploiement initial (voir spec `2026-09-18-zorionbot-v2-design.md`) :

```bash
tar -czf zorionbot-v2-deploy.tar.gz -C "<chemin worktree>" --exclude=.git --exclude=__pycache__ --exclude=.pytest_cache --exclude=.attic .
scp zorionbot-v2-deploy.tar.gz raspi-home:~/zorionbot-v2-deploy.tar.gz
ssh raspi-home "rm -rf ~/DonchianBot-v2/app ~/DonchianBot-v2/tests ~/DonchianBot-v2/docker-compose.yml && tar xzf ~/zorionbot-v2-deploy.tar.gz -C ~/DonchianBot-v2 && rm ~/zorionbot-v2-deploy.tar.gz"
ssh raspi-home "cd ~/DonchianBot-v2 && docker compose up -d --build"
```

- [ ] **Step 4: Vérifier le démarrage**

```bash
ssh raspi-home "docker logs donchianbot-v2 --tail 40"
```

Expected : connexion IG réussie (`Connected to IG Markets`), aucune trace d'erreur d'import (`ModuleNotFoundError`, `TypeError: Can't instantiate abstract class`), premier cycle programmé (`Next scan in ...s`).

- [ ] **Step 5: Vérifier le bot 1 non affecté**

```bash
ssh raspi-home "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep donchianbot; docker logs donchianbot --tail 5"
```

Expected : `donchianbot` toujours `Up`, dernier cycle normal, aucune erreur nouvelle.

- [ ] **Step 6: Attendre un signal réel et vérifier manuellement (hors plan — suivi manuel)**

Ce n'est pas un step automatisable : au prochain signal détecté par le bot 2, vérifier dans Telegram que 3 messages distincts arrivent (`Position 1/3`, `2/3`, `3/3`), puis au premier TP1 touché, vérifier la réception du message de bascule breakeven et, via `/status`, que les SL affichés pour les positions 2/3 restantes ont bien été remontés.
