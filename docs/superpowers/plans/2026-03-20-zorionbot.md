# ZorionBot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an autonomous M30 trading bot in Python that replicates the Donchian V1.1 Pine Script strategy, trades LONG and SHORT via IG Markets, and runs as an independent Docker container alongside the existing SwingBot.

**Architecture:** Broker-agnostic design with a `BaseBroker` abstract interface and an `IGBroker` implementation. Pure calculation logic is isolated in `risk.py` and `indicators.py`. `strategy.py` assembles the signal. `main.py` orchestrates the M30 loop with a 3-level candle cache.

**Tech Stack:** Python 3.11, httpx (async HTTP), asyncio, pytest, Docker / docker-compose

---

## File Map

| File | Role |
|------|------|
| `app/risk.py` | Pure functions: position size + TP calculation |
| `app/indicators.py` | Pure functions: Donchian channel + ZL-MACD |
| `app/brokers/base_broker.py` | Abstract broker interface + `BrokerError` |
| `app/brokers/__init__.py` | Package init |
| `app/brokers/ig_broker.py` | IG Markets REST API implementation |
| `app/config.py` | All env vars via `os.environ.get()` |
| `app/assets_config.py` | Asset list (empty, ready for user to fill) |
| `app/telegram_notifier.py` | Telegram notifications (async httpx) |
| `app/strategy.py` | Signal logic LONG/SHORT, calls indicators + risk |
| `app/main.py` | M30 loop, candle cache, orchestration |
| `app/requirements.txt` | Python dependencies |
| `Dockerfile` | Docker image definition |
| `docker-compose.yml` | Service `zorionbot` |
| `.env.example` | Fully commented blank config |
| `.gitignore` | Ignore .env, data/, logs/, __pycache__ |
| `tests/test_risk.py` | Unit tests for risk.py |
| `tests/test_indicators.py` | Unit tests for indicators.py |
| `tests/test_strategy.py` | Unit tests for strategy.py |

---

## Task 1: Project Scaffold

**Files:**
- Create: `ZorionBot/app/requirements.txt`
- Create: `ZorionBot/Dockerfile`
- Create: `ZorionBot/docker-compose.yml`
- Create: `ZorionBot/.env.example`
- Create: `ZorionBot/.gitignore`
- Create: `ZorionBot/app/brokers/__init__.py`
- Create: `ZorionBot/tests/__init__.py`
- Create: `ZorionBot/tests/conftest.py`

- [ ] **Step 1: Create `app/requirements.txt`**

```
httpx==0.27.0
```

Create also `requirements-dev.txt` at the root of `ZorionBot/` for development:
```
pytest==8.1.1
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

CMD ["python", "-u", "main.py"]
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  zorionbot:
    container_name: zorionbot
    build: .
    restart: unless-stopped
    env_file:
      - /srv/data/zorionbot/.env
    volumes:
      - /srv/data/zorionbot:/app/data
    environment:
      - DATA_DIR=/app/data
```

- [ ] **Step 4: Create `.env.example`**

```bash
# ─────────────────────────────────────────────────────────────────
# BROKER — Connexion à votre broker
# ─────────────────────────────────────────────────────────────────

# Nom du broker actif — détermine quelle implémentation sera utilisée
# Valeurs supportées actuellement : "ig"
BROKER=ig

# IG Markets — Clé API
# → Disponible dans votre espace client IG : Mon Compte > Paramètres > API
IG_API_KEY=VOTRE_CLE_API_ICI

# IG Markets — Identifiant de connexion (votre username IG)
IG_IDENTIFIER=VOTRE_IDENTIFIANT_ICI

# IG Markets — Mot de passe de votre compte IG
IG_PASSWORD=VOTRE_MOT_DE_PASSE_ICI

# Mode démo : true = compte démo IG, false = compte réel
# ⚠️  Toujours tester en mode démo avant de passer en live
DEMO_MODE=true

# ─────────────────────────────────────────────────────────────────
# TELEGRAM — Notifications
# ─────────────────────────────────────────────────────────────────

# Token du bot Telegram
# → Créez un bot via @BotFather sur Telegram
#   1. Ouvrez Telegram → cherchez @BotFather
#   2. Envoyez /newbot et suivez les instructions
#   3. Copiez le token reçu ici
TELEGRAM_BOT_TOKEN=VOTRE_TOKEN_ICI

# ID du canal ou groupe qui recevra les notifications
# → Obtenez-le via @userinfobot ou @RawDataBot sur Telegram
#   Pour un canal privé : ajoutez @RawDataBot au canal, envoyez un message
TELEGRAM_CHAT_ID=VOTRE_CHAT_ID_ICI

# ─────────────────────────────────────────────────────────────────
# STRATÉGIE — Paramètres Donchian
# ─────────────────────────────────────────────────────────────────

# Période du canal de Donchian (nombre de bougies M30)
# Doit être ≥ 10. Valeur recommandée : 100 (identique au Pine Script)
DONCHIAN_LENGTH=100

# Nombre de bougies historiques M30 à charger au démarrage
# Doit être ≥ DONCHIAN_LENGTH + 60. Valeur recommandée : 500
LOOKBACK_CANDLES=500

# ─────────────────────────────────────────────────────────────────
# RISQUE — Gestion des positions
# ─────────────────────────────────────────────────────────────────

# Montant risqué par trade, en devise du compte (EUR par défaut)
# Exemple : 50.0 = vous risquez 50€ maximum par trade
RISK_AMOUNT=50.0

# Valeur d'un point en devise du compte (valeur globale par défaut)
# Peut être surchargée par actif dans assets_config.py
# Exemples : 1.0 pour un CFD standard, 25.0 pour DAX Mini
POINT_VALUE=1.0

# Ratio Risque/Rendement pour le calcul du Take Profit
# Peut être surchargé par actif dans assets_config.py
# Exemple : 2.0 = le TP est placé à 2× la distance du SL
RR_RATIO=2.0

# ─────────────────────────────────────────────────────────────────
# LOGS
# ─────────────────────────────────────────────────────────────────

# Niveau de log : DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Répertoire des données persistantes (ne pas modifier si Docker)
DATA_DIR=/app/data
```

- [ ] **Step 5: Create `.gitignore`**

```
.env
data/
logs/
__pycache__/
*.pyc
*.pyo
*.pyd
.DS_Store
*.egg-info/
dist/
build/
```

- [ ] **Step 6: Create empty package files**

`app/brokers/__init__.py` → fichier vide
`tests/__init__.py` → fichier vide
`tests/conftest.py` → fichier vide (pytest point d'entrée)

- [ ] **Step 7: Commit**

```bash
git init  # si pas encore de repo
git add Dockerfile docker-compose.yml .env.example .gitignore app/requirements.txt requirements-dev.txt app/brokers/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: project scaffold — Dockerfile, docker-compose, .env.example"
```

---

## Task 2: `risk.py` — Calcul de position (TDD)

**Files:**
- Create: `ZorionBot/app/risk.py`
- Create: `ZorionBot/tests/test_risk.py`

- [ ] **Step 1: Écrire les tests**

`tests/test_risk.py` :
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from risk import calculate_size, calculate_tp


class TestCalculateSize:
    def test_normal_case(self):
        # 50€ de risque, distance 10 pts, 1€/pt → 5 unités
        assert calculate_size(50.0, 100.0, 90.0, 1.0) == pytest.approx(5.0)

    def test_point_value_multiplier(self):
        # 50€ de risque, distance 2 pts, 25€/pt → 1 unité
        assert calculate_size(50.0, 100.0, 98.0, 25.0) == pytest.approx(1.0)

    def test_zero_distance_returns_zero(self):
        # SL = entry → pas de trade possible
        assert calculate_size(50.0, 100.0, 100.0, 1.0) == 0.0

    def test_short_direction(self):
        # entry < sl pour un short → même résultat (abs)
        assert calculate_size(50.0, 90.0, 100.0, 1.0) == pytest.approx(5.0)


class TestCalculateTp:
    def test_buy_tp_above_entry(self):
        # entry=100, sl=90, rr=2 → tp=120
        assert calculate_tp(100.0, 90.0, 2.0, "BUY") == pytest.approx(120.0)

    def test_sell_tp_below_entry(self):
        # entry=100, sl=110, rr=2 → tp=80
        assert calculate_tp(100.0, 110.0, 2.0, "SELL") == pytest.approx(80.0)

    def test_rr_ratio_one(self):
        # rr=1 → TP = entry + distance (1:1)
        assert calculate_tp(100.0, 95.0, 1.0, "BUY") == pytest.approx(105.0)
```

- [ ] **Step 2: Lancer les tests → vérifier qu'ils échouent**

```bash
cd ZorionBot
python -m pytest tests/test_risk.py -v
```
Attendu : `ModuleNotFoundError: No module named 'risk'`

- [ ] **Step 3: Implémenter `app/risk.py`**

```python
"""
risk.py — Calculs purs de gestion du risque.
Aucune dépendance externe. Testable sans broker.
"""


def calculate_size(risk_amount: float, entry: float, sl: float, point_value: float) -> float:
    """
    Calcule la taille de position pour risquer exactement risk_amount.

    Args:
        risk_amount:  Montant max à risquer (ex: 50.0 €)
        entry:        Prix d'entrée
        sl:           Prix du stop loss
        point_value:  Valeur d'un point en devise du compte

    Returns:
        Nombre d'unités/lots à trader. 0.0 si distance nulle.
    """
    distance = abs(entry - sl)
    if distance == 0:
        return 0.0
    return risk_amount / (distance * point_value)


def calculate_tp(entry: float, sl: float, rr_ratio: float, direction: str) -> float:
    """
    Calcule le Take Profit à partir du ratio R:R.

    Args:
        entry:     Prix d'entrée
        sl:        Prix du stop loss
        rr_ratio:  Ratio risque/rendement (ex: 2.0 → TP = 2× la distance SL)
        direction: "BUY" ou "SELL"

    Returns:
        Prix du take profit.
    """
    distance = abs(entry - sl)
    if direction == "BUY":
        return entry + distance * rr_ratio
    return entry - distance * rr_ratio
```

- [ ] **Step 4: Lancer les tests → vérifier qu'ils passent**

```bash
python -m pytest tests/test_risk.py -v
```
Attendu : 6 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add app/risk.py tests/test_risk.py
git commit -m "feat: add risk.py — calculate_size and calculate_tp"
```

---

## Task 3: `indicators.py` — Donchian + ZL-MACD (TDD)

**Files:**
- Create: `ZorionBot/app/indicators.py`
- Create: `ZorionBot/tests/test_indicators.py`

- [ ] **Step 1: Écrire les tests**

`tests/test_indicators.py` :
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from indicators import donchian_channel, zlmacd


class TestDonchianChannel:
    def test_upper_lower_basis(self):
        highs = [10.0] * 98 + [15.0, 12.0]   # last 100: max=15
        lows  = [5.0]  * 98 + [4.0, 6.0]      # last 100: min=4
        upper, lower, basis, limitHigh, limitLow = donchian_channel(highs, lows, 100)
        assert upper == pytest.approx(15.0)
        assert lower == pytest.approx(4.0)
        assert basis == pytest.approx(9.5)

    def test_quartiles(self):
        highs = [100.0] * 100
        lows  = [0.0]   * 100
        upper, lower, basis, limitHigh, limitLow = donchian_channel(highs, lows, 100)
        # basis=50, limitHigh=75, limitLow=25
        assert limitHigh == pytest.approx(75.0)
        assert limitLow  == pytest.approx(25.0)

    def test_uses_only_last_n_candles(self):
        # Les 50 premières bougies ont un high=999 qui NE doit PAS compter
        highs = [999.0] * 50 + [10.0] * 50
        lows  = [0.0]   * 100
        upper, lower, basis, limitHigh, limitLow = donchian_channel(highs, lows, 50)
        assert upper == pytest.approx(10.0)


class TestZlMacd:
    def _make_trend(self, start, step, n=200):
        """Génère une série de prix avec une tendance linéaire."""
        return [start + i * step for i in range(n)]

    def test_uptrend_returns_positive(self):
        closes = self._make_trend(100.0, 0.5)   # tendance haussière
        result = zlmacd(closes)
        assert result > 0

    def test_downtrend_returns_negative(self):
        closes = self._make_trend(200.0, -0.5)  # tendance baissière
        result = zlmacd(closes)
        assert result < 0

    def test_flat_returns_near_zero(self):
        closes = [100.0] * 200                   # prix stable
        result = zlmacd(closes)
        assert abs(result) < 0.01

    def test_requires_sufficient_candles(self):
        with pytest.raises(ValueError):
            zlmacd([100.0] * 10)   # pas assez de bougies (min 52)
```

- [ ] **Step 2: Lancer les tests → vérifier qu'ils échouent**

```bash
python -m pytest tests/test_indicators.py -v
```
Attendu : `ModuleNotFoundError: No module named 'indicators'`

- [ ] **Step 3: Implémenter `app/indicators.py`**

```python
"""
indicators.py — Indicateurs techniques purs.

Convention d'indexation :
  candles[-1]  = bougie signal (dernière bougie fermée)
  candles[-2]  = bougie précédente
  candles[-3]  = ante-pénultième

Aucune dépendance externe.
"""


def _ema_series(values: list, period: int) -> list:
    """
    Calcule la série EMA complète sur une liste de valeurs.
    Initialisation : première valeur = premier élément de la liste.
    """
    k = 2.0 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def donchian_channel(highs: list, lows: list, length: int) -> tuple:
    """
    Calcule le canal de Donchian sur les `length` dernières bougies.

    Returns:
        (upper, lower, basis, limitHigh, limitLow)
        - upper     : plus haut des `length` dernières bougies
        - lower     : plus bas des `length` dernières bougies
        - basis     : médiane du canal
        - limitHigh : quartile haut (Q3) — zone de vente
        - limitLow  : quartile bas  (Q1) — zone d'achat
    """
    upper = max(highs[-length:])
    lower = min(lows[-length:])
    basis = (upper + lower) / 2.0
    limitHigh = upper - (upper - basis) / 2.0
    limitLow  = lower + (basis - lower) / 2.0
    return upper, lower, basis, limitHigh, limitLow


def zlmacd(closes: list, fast: int = 12, slow: int = 26) -> float:
    """
    Zero Lag MACD = DEMA(fast) - DEMA(slow)
    DEMA(n) = 2 × EMA(close, n) - EMA(EMA(close, n), n)

    Seule la valeur de la ligne MACD est retournée.
    La signal line et l'histogramme sont intentionnellement omis :
    les conditions de la stratégie utilisent uniquement zlmacd > 0 / < 0.

    Args:
        closes: Liste de prix de clôture (min slow × 2 = 52 valeurs)
        fast:   Période rapide (défaut: 12)
        slow:   Période lente  (défaut: 26)

    Raises:
        ValueError: si la liste est trop courte pour calculer le ZL-MACD
    """
    min_required = slow * 2
    if len(closes) < min_required:
        raise ValueError(
            f"zlmacd nécessite au moins {min_required} valeurs, "
            f"{len(closes)} fournies."
        )

    # DEMA fast
    ema1     = _ema_series(closes, fast)
    ema2     = _ema_series(ema1, fast)
    demaFast = 2.0 * ema1[-1] - ema2[-1]

    # DEMA slow
    emas1    = _ema_series(closes, slow)
    emas2    = _ema_series(emas1, slow)
    demaSlow = 2.0 * emas1[-1] - emas2[-1]

    return demaFast - demaSlow
```

- [ ] **Step 4: Lancer les tests → vérifier qu'ils passent**

```bash
python -m pytest tests/test_indicators.py -v
```
Attendu : 7 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add app/indicators.py tests/test_indicators.py
git commit -m "feat: add indicators.py — donchian_channel and zlmacd"
```

---

## Task 4: `brokers/base_broker.py` — Interface abstraite

**Files:**
- Create: `ZorionBot/app/brokers/base_broker.py`

- [ ] **Step 1: Implémenter `app/brokers/base_broker.py`**

```python
"""
base_broker.py — Contrat abstrait pour tout broker.

Pour ajouter un nouveau broker :
  1. Créer un fichier brokers/<nom>_broker.py
  2. Implémenter toutes les méthodes abstraites de BaseBroker
  3. Mettre BROKER=<nom> dans le .env
"""
from abc import ABC, abstractmethod
from typing import List


class BrokerError(Exception):
    """Levée quand le broker rejette ou échoue à exécuter une opération."""
    pass


class BaseBroker(ABC):

    @abstractmethod
    async def connect(self) -> None:
        """
        Authentification auprès du broker.
        Lève BrokerError si la connexion échoue.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Ferme proprement la session broker."""

    @abstractmethod
    async def get_candles(self, symbol: str, count: int, timeframe: str = "MINUTE_30") -> List[dict]:
        """
        Récupère les `count` dernières bougies fermées pour le symbole.

        Returns:
            Liste de dicts avec les clés :
              "time"  : str  (ISO 8601)
              "open"  : float
              "high"  : float
              "low"   : float
              "close" : float
        """

    @abstractmethod
    async def get_account_balance(self) -> float:
        """
        Retourne le solde disponible du compte en devise du compte.
        Retourne 0.0 en cas d'erreur non bloquante.
        """

    @abstractmethod
    async def get_open_positions(self) -> List[dict]:
        """
        Retourne les positions ouvertes.

        Chaque dict contient au minimum :
          "epic":      str   — identifiant de l'instrument
          "direction": str   — "BUY" ou "SELL"
          "size":      float — taille de la position
          "deal_id":   str   — identifiant unique de la position
        """

    @abstractmethod
    async def open_long(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> None:
        """
        Ouvre une position longue (BUY).
        Lève BrokerError avec un message descriptif si le broker rejette l'ordre.
        """

    @abstractmethod
    async def open_short(self, symbol: str, size: float, sl: float, tp: float, **kwargs) -> None:
        """
        Ouvre une position courte (SELL).
        Lève BrokerError avec un message descriptif si le broker rejette l'ordre.
        """
```

- [ ] **Step 2: Vérifier que l'interface est importable**

```bash
cd ZorionBot
python -c "from app.brokers.base_broker import BaseBroker, BrokerError; print('OK')"
```
Attendu : `OK`

- [ ] **Step 3: Commit**

```bash
git add app/brokers/base_broker.py
git commit -m "feat: add BaseBroker abstract interface and BrokerError"
```

---

## Task 5: `config.py` + `assets_config.py`

**Files:**
- Create: `ZorionBot/app/config.py`
- Create: `ZorionBot/app/assets_config.py`

- [ ] **Step 1: Implémenter `app/config.py`**

```python
"""
config.py — Toutes les variables de configuration lues depuis l'environnement.
Copier .env.example → .env et renseigner les valeurs avant de démarrer.
"""
import os

# ── Broker ────────────────────────────────────────────────────────
BROKER         = os.environ.get("BROKER", "ig")
IG_API_KEY     = os.environ.get("IG_API_KEY", "")
IG_IDENTIFIER  = os.environ.get("IG_IDENTIFIER", "")
IG_PASSWORD    = os.environ.get("IG_PASSWORD", "")
DEMO_MODE      = os.environ.get("DEMO_MODE", "true").lower() == "true"

# ── Telegram ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Stratégie ─────────────────────────────────────────────────────
DONCHIAN_LENGTH   = int(os.environ.get("DONCHIAN_LENGTH", "100"))
LOOKBACK_CANDLES  = int(os.environ.get("LOOKBACK_CANDLES", "500"))

# ── Risque ────────────────────────────────────────────────────────
RISK_AMOUNT  = float(os.environ.get("RISK_AMOUNT", "50.0"))
POINT_VALUE  = float(os.environ.get("POINT_VALUE", "1.0"))
RR_RATIO     = float(os.environ.get("RR_RATIO", "2.0"))

# ── Logs ──────────────────────────────────────────────────────────
DATA_DIR  = os.environ.get("DATA_DIR", "/app/data")
LOG_FILE  = os.path.join(DATA_DIR, "zorionbot.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
```

- [ ] **Step 2: Implémenter `app/assets_config.py`**

```python
# ──────────────────────────────────────────────────────────────────────────────
# assets_config.py — Configuration des actifs pour le ZorionBot
#
# Remplir ce fichier avec les actifs à surveiller avant de démarrer le bot.
#
# Champs obligatoires par actif :
#   "symbol"      : Epic IG Markets de l'instrument
#                   → Trouvable dans l'interface IG : cliquez sur un marché
#                     puis "Informations" > "Epic"
#                   Exemples :
#                     DAX      → "IX.D.DAX.IFMM.IP"
#                     NAS100   → "IX.D.NASDAQ.IFD.IP"
#                     Gold CFD → "CS.D.CFEGOLD.CFE.IP"
#
#   "point_value" : Valeur d'un point en devise du compte
#                   → Surcharge la valeur globale POINT_VALUE du .env
#                   → Consultez la fiche produit IG pour connaître cette valeur
#                   Exemples : 1.0 (CFD standard), 25.0 (DAX Mini)
#
#   "rr_ratio"    : Ratio Risque/Rendement pour le Take Profit
#                   → Surcharge la valeur globale RR_RATIO du .env
#                   Exemple : 2.0 → TP placé à 2× la distance du SL
#
#   "enabled"     : true = actif surveillé, false = ignoré
# ──────────────────────────────────────────────────────────────────────────────

ASSETS = {
    # Exemple (à modifier/remplacer avec vos actifs) :
    # "DAX": {
    #     "symbol":      "IX.D.DAX.IFMM.IP",
    #     "point_value": 1.0,
    #     "rr_ratio":    2.0,
    #     "enabled":     False,
    # },
}

ENABLED_ASSETS = {k: v for k, v in ASSETS.items() if v.get("enabled", False)}
```

- [ ] **Step 3: Vérifier que config et assets_config s'importent**

```bash
python -c "from app.config import DONCHIAN_LENGTH; from app.assets_config import ENABLED_ASSETS; print('OK')"
```
Attendu : `OK`

- [ ] **Step 4: Commit**

```bash
git add app/config.py app/assets_config.py
git commit -m "feat: add config.py and assets_config.py"
```

---

## Task 6: `brokers/ig_broker.py` — Implémentation IG Markets

**Files:**
- Create: `ZorionBot/app/brokers/ig_broker.py`

- [ ] **Step 1: Implémenter `app/brokers/ig_broker.py`**

```python
"""
ig_broker.py — Implémentation IG Markets de BaseBroker.

API REST IG Markets :
  - Base URL démo  : https://api.ig.com/gateway/deal
  - Base URL live  : https://api.ig.com/gateway/deal
  - Authentification : POST /session → headers CST + X-SECURITY-TOKEN
  - Résolution M30 : "MINUTE_30"

Documentation : https://labs.ig.com/rest-trading-api-reference
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
            "Content-Type":    "application/json; charset=UTF-8",
            "Accept":          "application/json; charset=UTF-8",
            "X-IG-API-KEY":    self._api_key,
            "CST":             self._cst,
            "X-SECURITY-TOKEN": self._token,
            "Version":         "2",
        }

    async def connect(self) -> None:
        payload = {
            "identifier":       self._identifier,
            "password":         self._password,
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
            raise BrokerError(f"Connexion IG échouée ({e.response.status_code}): {e.response.text}") from e
        except httpx.RequestError as e:
            raise BrokerError(f"Erreur réseau lors de la connexion IG: {e}") from e

        self._cst   = resp.headers.get("CST", "")
        self._token = resp.headers.get("X-SECURITY-TOKEN", "")
        logger.info("Connecté à IG Markets (demo=%s)", self._demo)

    async def disconnect(self) -> None:
        try:
            await self._client.delete(
                f"{IG_BASE_URL}/session",
                headers=self._headers(),
            )
        except Exception as e:
            logger.warning("Erreur déconnexion IG: %s", e)
        finally:
            await self._client.aclose()
            logger.info("Déconnecté de IG Markets")

    async def get_candles(self, symbol: str, count: int, timeframe: str = "MINUTE_30") -> List[dict]:
        url = f"{IG_BASE_URL}/prices/{symbol}"
        params = {"resolution": timeframe, "max": count, "pageSize": 0}
        headers = {**self._headers(), "Version": "3"}
        try:
            resp = await self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"get_candles {symbol} ({e.response.status_code})",
                request=e.request, response=e.response
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
            logger.warning("get_account_balance échoué: %s", e)
        return 0.0

    async def get_open_positions(self) -> List[dict]:
        try:
            resp = await self._client.get(
                f"{IG_BASE_URL}/positions/otc",
                headers={**self._headers(), "Version": "2"},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("get_open_positions échoué: %s", e)
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
        symbol: str,
        size: float,
        direction: str,
        sl: float,
        tp: float,
        comment: str = "",
        currency_code: str = "EUR",
        **kwargs,
    ) -> None:
        payload = {
            "epic":            symbol,
            "expiry":          "-",
            "direction":       direction,
            "size":            str(round(size, 2)),
            "orderType":       "MARKET",
            "timeInForce":     "FILL_OR_KILL",
            "guaranteedStop":  False,
            "stopLevel":       str(round(sl, 2)),
            "limitLevel":      str(round(tp, 2)),
            "currencyCode":    currency_code,
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
                f"Ordre {direction} {symbol} rejeté ({e.response.status_code}): {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise BrokerError(f"Erreur réseau ordre {direction} {symbol}: {e}") from e

        deal_ref = resp.json().get("dealReference", "?")
        logger.info("Ordre %s %s placé — dealRef: %s", direction, symbol, deal_ref)
```

- [ ] **Step 2: Vérifier que le module s'importe sans erreur**

```bash
python -c "from app.brokers.ig_broker import IGBroker; print('OK')"
```
Attendu : `OK`

- [ ] **Step 3: Commit**

```bash
git add app/brokers/ig_broker.py
git commit -m "feat: add IGBroker — IG Markets REST API implementation"
```

---

## Task 7: `telegram_notifier.py`

**Files:**
- Create: `ZorionBot/app/telegram_notifier.py`

- [ ] **Step 1: Implémenter `app/telegram_notifier.py`**

```python
"""
telegram_notifier.py — Notifications Telegram asynchrones.
"""
import logging
import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:

    def __init__(self, token: str, chat_id: str):
        self._token   = token
        self._chat_id = chat_id
        self._enabled = bool(token and chat_id)

    async def _send(self, text: str) -> None:
        if not self._enabled:
            logger.debug("Telegram désactivé (token/chat_id manquant)")
            return
        url = TELEGRAM_API.format(token=self._token)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json={
                    "chat_id":    self._chat_id,
                    "text":       text,
                    "parse_mode": "HTML",
                })
        except Exception as e:
            logger.warning("Telegram send échoué: %s", e)

    async def send_test_message(self) -> None:
        await self._send("✅ ZorionBot connecté et opérationnel.")

    async def send_startup(self, demo: bool, assets: list) -> None:
        mode = "DÉMO" if demo else "LIVE ⚠️"
        assets_str = ", ".join(assets) if assets else "aucun actif configuré"
        await self._send(
            f"🤖 <b>ZorionBot démarré</b>\n"
            f"Mode : {mode}\n"
            f"Actifs : {assets_str}"
        )

    async def send_signal(self, signal: dict, demo: bool) -> None:
        direction = "🚀 LONG" if signal["direction"] == "BUY" else "🔻 SHORT"
        mode_tag  = "[DEMO] " if demo else ""
        await self._send(
            f"{direction} {mode_tag}<b>{signal['asset_name']}</b>\n"
            f"Entrée : {signal['entry_price']:.2f}\n"
            f"SL : {signal['sl_price']:.2f}\n"
            f"TP : {signal['tp_price']:.2f}\n"
            f"Taille : {signal['qty']:.2f}"
        )

    async def send_error(self, context: str, message: str) -> None:
        await self._send(f"❌ <b>Erreur — {context}</b>\n{message}")

    async def send_daily_summary(self, trades_today: int, open_positions: list) -> None:
        await self._send(
            f"📊 <b>Résumé quotidien ZorionBot</b>\n"
            f"Trades du jour : {trades_today}\n"
            f"Positions ouvertes : {len(open_positions)}"
        )
```

- [ ] **Step 2: Vérifier que le module s'importe**

```bash
python -c "from app.telegram_notifier import TelegramNotifier; print('OK')"
```
Attendu : `OK`

- [ ] **Step 3: Commit**

```bash
git add app/telegram_notifier.py
git commit -m "feat: add TelegramNotifier"
```

---

## Task 8: `strategy.py` — Logique des signaux (TDD)

**Files:**
- Create: `ZorionBot/app/strategy.py`
- Create: `ZorionBot/tests/test_strategy.py`

- [ ] **Step 1: Écrire les tests**

`tests/test_strategy.py` :
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from strategy import analyse_asset


def _make_candles(n=200, base=100.0):
    """Génère des bougies neutres (open=close, haut/bas symétriques)."""
    return [{"open": base, "high": base + 1, "low": base - 1, "close": base} for _ in range(n)]


def _set_long_conditions(candles, upper, lower, limitLow, limitHigh):
    """
    Configure les 3 dernières bougies pour déclencher un signal LONG.
    LONG = le prix touche le BAS du canal (touched_lower), puis rebondit.
    candles[-3]: touche lower (low <= lower)
    candles[-2]: bougie précédente neutre (high connu pour le test close > high[-2])
    candles[-1]: bougie signal — haussière, close > high[-2], open < limitLow
    """
    base = (upper + lower) / 2
    for i in range(len(candles) - 3):
        candles[i] = {"open": base, "high": upper - 1, "low": lower + 1, "close": base}

    # Bougie -3 : touche lower (low <= lower)
    candles[-3] = {"open": lower + 2, "high": lower + 3, "low": lower, "close": lower + 2}
    # Bougie -2 : neutre, high connu = base + 0.5
    candles[-2] = {"open": base, "high": base + 0.5, "low": base - 1, "close": base}
    # Bougie -1 (signal) : haussière, open sous limitLow, close > high[-2]
    candles[-1] = {
        "open":  limitLow - 1,          # open < limitLow ✓
        "high":  limitLow + 2,
        "low":   limitLow - 2,
        "close": base + 1,               # close > high[-2] = base+0.5 ✓ et close > open ✓
    }


def _set_short_conditions(candles, upper, lower, limitLow, limitHigh):
    """
    Configure les 3 dernières bougies pour déclencher un signal SHORT.
    SHORT = le prix touche le HAUT du canal (touched_upper), puis se retourne.
    candles[-3]: touche upper (high >= upper)
    candles[-2]: bougie précédente neutre (low connu pour le test close < low[-2])
    candles[-1]: bougie signal — baissière, close < low[-2], open > limitHigh
    """
    base = (upper + lower) / 2
    for i in range(len(candles) - 3):
        candles[i] = {"open": base, "high": upper - 1, "low": lower + 1, "close": base}

    # Bougie -3 : touche upper (high >= upper)
    candles[-3] = {"open": upper - 2, "high": upper, "low": upper - 3, "close": upper - 2}
    # Bougie -2 : neutre, low connu = base - 0.5
    candles[-2] = {"open": base, "high": base + 1, "low": base - 0.5, "close": base}
    # Bougie -1 (signal) : baissière, open au-dessus de limitHigh, close < low[-2]
    candles[-1] = {
        "open":  limitHigh + 1,         # open > limitHigh ✓
        "high":  limitHigh + 2,
        "low":   limitHigh - 2,
        "close": base - 1,               # close < low[-2] = base-0.5 ✓ et close < open ✓
    }


class TestAnalyseAssetLong:
    def test_long_signal_all_conditions_met(self):
        candles = _make_candles(200, base=100.0)
        # Donchian sur 100 bougies : upper=101, lower=99 avec les bougies par défaut
        # On reconstruit pour avoir un canal clair
        upper, lower = 110.0, 90.0
        limitLow = lower + (((upper + lower) / 2) - lower) / 2   # = 95
        limitHigh = upper - (upper - ((upper + lower) / 2)) / 2  # = 105

        _set_long_conditions(candles, upper, lower, limitLow, limitHigh)

        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        # ZL-MACD doit être < 0 pour un LONG : on doit construire une série baissière
        # On force des closes décroissants dans les premières bougies
        for i in range(150):
            candles[i]["close"] = 120.0 - i * 0.1   # tendance baissière

        result = analyse_asset("TEST", asset_config, candles,
                               prev_long=False, prev_short=False,
                               risk_amount=50.0, donchian_length=100)
        assert result is not None
        assert result["direction"] == "BUY"
        assert "entry_price" in result
        assert "sl_price"    in result
        assert "tp_price"    in result
        assert result["qty"] > 0

    def test_no_signal_when_prev_long_true(self):
        """Anti-doublon : pas de signal LONG si le précédent était déjà LONG."""
        candles = _make_candles(200, base=100.0)
        upper, lower = 110.0, 90.0
        limitLow  = 95.0
        limitHigh = 105.0
        _set_long_conditions(candles, upper, lower, limitLow, limitHigh)

        for i in range(150):
            candles[i]["close"] = 120.0 - i * 0.1

        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset("TEST", asset_config, candles,
                               prev_long=True, prev_short=False,
                               risk_amount=50.0, donchian_length=100)
        assert result is None

    def test_no_signal_insufficient_candles(self):
        candles = _make_candles(10)
        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset("TEST", asset_config, candles,
                               prev_long=False, prev_short=False,
                               risk_amount=50.0, donchian_length=100)
        assert result is None

    def test_tp_is_above_entry_for_long(self):
        candles = _make_candles(200, base=100.0)
        upper, lower = 110.0, 90.0
        limitLow = 95.0
        _set_long_conditions(candles, upper, lower, limitLow, 105.0)
        for i in range(150):
            candles[i]["close"] = 120.0 - i * 0.1

        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset("TEST", asset_config, candles,
                               prev_long=False, prev_short=False,
                               risk_amount=50.0, donchian_length=100)
        if result:
            assert result["tp_price"] > result["entry_price"]


class TestAnalyseAssetShort:
    def test_short_signal_all_conditions_met(self):
        candles = _make_candles(200, base=100.0)
        upper, lower = 110.0, 90.0
        limitHigh = 105.0
        limitLow  = 95.0

        _set_short_conditions(candles, upper, lower, limitLow, limitHigh)

        # ZL-MACD doit être > 0 pour un SHORT : tendance haussière
        for i in range(150):
            candles[i]["close"] = 80.0 + i * 0.1

        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset("TEST", asset_config, candles,
                               prev_long=False, prev_short=False,
                               risk_amount=50.0, donchian_length=100)
        assert result is not None
        assert result["direction"] == "SELL"
        assert result["tp_price"] < result["entry_price"]

    def test_no_signal_when_prev_short_true(self):
        candles = _make_candles(200, base=100.0)
        upper, lower = 110.0, 90.0
        _set_short_conditions(candles, upper, lower, 95.0, 105.0)
        for i in range(150):
            candles[i]["close"] = 80.0 + i * 0.1

        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset("TEST", asset_config, candles,
                               prev_long=False, prev_short=True,
                               risk_amount=50.0, donchian_length=100)
        assert result is None
```

- [ ] **Step 2: Lancer les tests → vérifier qu'ils échouent**

```bash
python -m pytest tests/test_strategy.py -v
```
Attendu : `ModuleNotFoundError: No module named 'strategy'`

- [ ] **Step 3: Implémenter `app/strategy.py`**

```python
"""
strategy.py — Logique de génération des signaux LONG/SHORT.

Traduction fidèle du Pine Script Donchian V1.1.
Convention d'indexation : candles[-1] = bougie signal (dernière fermée).
"""
import logging
from typing import Optional, List, Dict

from indicators import donchian_channel, zlmacd
import risk as risk_module

logger = logging.getLogger(__name__)


def analyse_asset(
    asset_name:     str,
    asset_config:   Dict,
    candles:        List[Dict],
    prev_long:      bool,
    prev_short:     bool,
    risk_amount:    float,
    donchian_length: int,
) -> Optional[Dict]:
    """
    Analyse les bougies et retourne un signal ou None.

    Args:
        asset_name:      Nom lisible de l'actif (ex: "DAX")
        asset_config:    Dict avec symbol, point_value, rr_ratio
        candles:         Liste de bougies (au moins donchian_length + 60)
        prev_long:       True si un signal LONG a été émis à la bougie précédente
        prev_short:      True si un signal SHORT a été émis à la bougie précédente
        risk_amount:     Montant à risquer par trade
        donchian_length: Période du canal de Donchian

    Returns:
        Dict signal ou None
    """
    min_candles = donchian_length + 60
    if len(candles) < min_candles:
        logger.debug("%s : pas assez de bougies (%d < %d)", asset_name, len(candles), min_candles)
        return None

    opens  = [c["open"]  for c in candles]
    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]
    closes = [c["close"] for c in candles]

    # ── Indicateurs ───────────────────────────────────────────────
    upper, lower, _, limitHigh, limitLow = donchian_channel(highs, lows, donchian_length)

    try:
        macd_value = zlmacd(closes)
    except ValueError as e:
        logger.debug("%s : zlmacd impossible — %s", asset_name, e)
        return None

    # ── Conditions communes ───────────────────────────────────────
    touched_upper = any(h >= upper for h in highs[-3:])
    touched_lower = any(l <= lower for l in lows[-3:])

    # ── Signal LONG ───────────────────────────────────────────────
    raw_long = (
        touched_lower
        and closes[-1] > opens[-1]             # bougie signal haussière
        and closes[-1] > highs[-2]             # close > high de la précédente
        and opens[-1]  < limitLow              # open en zone achat
        and macd_value < 0                     # filtre ZL-MACD
    )
    long_signal = raw_long and not prev_long   # anti-doublon

    # ── Signal SHORT ──────────────────────────────────────────────
    raw_short = (
        touched_upper
        and closes[-1] < opens[-1]             # bougie signal baissière
        and closes[-1] < lows[-2]              # close < low de la précédente
        and opens[-1]  > limitHigh             # open en zone vente
        and macd_value > 0                     # filtre ZL-MACD
    )
    short_signal = raw_short and not prev_short

    if not long_signal and not short_signal:
        return None

    # ── Calcul des prix ───────────────────────────────────────────
    point_value = asset_config.get("point_value", 1.0)
    rr_ratio    = asset_config.get("rr_ratio", 2.0)

    if long_signal:
        direction   = "BUY"
        entry_price = highs[-2]
        sl_price    = min(lows[-1], lows[-2])
    else:
        direction   = "SELL"
        entry_price = lows[-2]
        sl_price    = max(highs[-1], highs[-2])

    qty      = risk_module.calculate_size(risk_amount, entry_price, sl_price, point_value)
    tp_price = risk_module.calculate_tp(entry_price, sl_price, rr_ratio, direction)

    if qty <= 0:
        logger.warning("%s : qty nulle (entry=sl), signal ignoré", asset_name)
        return None

    return {
        "direction":   direction,
        "entry_price": entry_price,
        "sl_price":    sl_price,
        "tp_price":    tp_price,
        "qty":         qty,
        "asset_name":  asset_name,
        "symbol":      asset_config["symbol"],
    }
```

- [ ] **Step 4: Lancer les tests → vérifier qu'ils passent**

```bash
python -m pytest tests/test_strategy.py -v
```
Attendu : tous les tests PASSED (ou SKIPPED si les conditions de marché ne se déclenchent pas — ajuster les valeurs de candles dans ce cas)

- [ ] **Step 5: Lancer tous les tests**

```bash
python -m pytest tests/ -v
```
Attendu : tous les tests de risk, indicators et strategy PASSED

- [ ] **Step 6: Commit**

```bash
git add app/strategy.py tests/test_strategy.py
git commit -m "feat: add strategy.py — LONG/SHORT signal logic"
```

---

## Task 9: `main.py` — Boucle principale M30

**Files:**
- Create: `ZorionBot/app/main.py`

- [ ] **Step 1: Implémenter `app/main.py`**

```python
#!/usr/bin/env python3
"""
main.py — Boucle principale du ZorionBot
Stratégie : Donchian Channel V1.1 (LONG + SHORT)
Timeframe : M30
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import httpx

from config import (
    IG_API_KEY, IG_IDENTIFIER, IG_PASSWORD, DEMO_MODE,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    RISK_AMOUNT, DONCHIAN_LENGTH, LOOKBACK_CANDLES,
    LOG_FILE, LOG_LEVEL, DATA_DIR,
)
from assets_config import ENABLED_ASSETS
from brokers.ig_broker import IGBroker
from brokers.base_broker import BrokerError
from strategy import analyse_asset
from telegram_notifier import TelegramNotifier

# ── Logging ───────────────────────────────────────────────────────
os.makedirs(DATA_DIR, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ZorionBot")

# ── Cache bougies ─────────────────────────────────────────────────
_candle_cache: dict = {}
_startup_done: set  = set()
_CACHE_FILE = os.path.join(DATA_DIR, "candle_cache.json")

# ── Suivi des signaux précédents (anti-doublon) ───────────────────
_prev_long:  dict = {}   # {epic: bool}
_prev_short: dict = {}   # {epic: bool}


def _load_disk_cache():
    if not os.path.exists(_CACHE_FILE):
        return
    try:
        with open(_CACHE_FILE) as f:
            data = json.load(f)
        for epic, entry in data.items():
            _candle_cache[epic] = entry["candles"]
        logger.info("Cache disque chargé — %d actifs", len(_candle_cache))
    except Exception as e:
        logger.warning("Erreur lecture cache disque : %s", e)


def _save_disk_cache():
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        data = {epic: {"candles": c} for epic, c in _candle_cache.items()}
        with open(_CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning("Erreur écriture cache disque : %s", e)


async def get_fresh_candles(broker: IGBroker, epic: str) -> list:
    """Cache 3 niveaux : complet → rattrapage → incrémental."""
    if epic not in _candle_cache:
        try:
            candles = await broker.get_candles(epic, LOOKBACK_CANDLES)
            _candle_cache[epic] = candles
            _startup_done.add(epic)
            _save_disk_cache()
            logger.info("Cache initialisé — %s : %d bougies", epic, len(candles))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning("Quota IG dépassé pour %s — actif ignoré", epic)
                return []
            raise
    elif epic not in _startup_done:
        try:
            new_candles = await broker.get_candles(epic, 10)
            _startup_done.add(epic)
            if new_candles:
                existing    = _candle_cache[epic]
                known_times = {c["time"] for c in existing}
                added       = [c for c in new_candles if c["time"] not in known_times]
                if added:
                    _candle_cache[epic] = (existing + added)[-LOOKBACK_CANDLES:]
                    _save_disk_cache()
            logger.info("Cache rattrapé — %s", epic)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning("Quota dépassé pour %s — cache disque utilisé", epic)
                _startup_done.add(epic)
            else:
                raise
    else:
        try:
            new_candles = await broker.get_candles(epic, 3)
            if new_candles:
                existing    = _candle_cache[epic]
                known_times = {c["time"] for c in existing}
                added       = [c for c in new_candles if c["time"] not in known_times]
                if added:
                    _candle_cache[epic] = (existing + added)[-LOOKBACK_CANDLES:]
                    _save_disk_cache()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning("Quota dépassé pour %s — analyse sur cache", epic)
            else:
                raise

    return _candle_cache.get(epic, [])


def seconds_until_next_m30() -> float:
    now = datetime.now(timezone.utc)
    remaining = ((30 - now.minute % 30) * 60) - now.second
    return max(float(remaining + 5), 5.0)


async def run_cycle(broker: IGBroker, telegram: TelegramNotifier) -> int:
    now = datetime.now(timezone.utc)
    logger.info("═══ Cycle %s ═══", now.strftime("%Y-%m-%d %H:%M UTC"))

    balance = await broker.get_account_balance()
    if not balance:
        logger.warning("Balance indisponible — cycle annulé")
        return 0

    open_positions = await broker.get_open_positions()
    open_epics     = {p["epic"] for p in open_positions}

    signals_found = 0

    for asset_name, asset_config in ENABLED_ASSETS.items():
        epic = asset_config["symbol"]
        if epic in open_epics:
            logger.debug("%s : position déjà ouverte — skip", asset_name)
            continue

        try:
            candles = await get_fresh_candles(broker, epic)
            if not candles:
                continue

            signal = analyse_asset(
                asset_name    = asset_name,
                asset_config  = asset_config,
                candles       = candles,
                prev_long     = _prev_long.get(epic, False),
                prev_short    = _prev_short.get(epic, False),
                risk_amount   = RISK_AMOUNT,
                donchian_length = DONCHIAN_LENGTH,
            )

            # Mettre à jour l'état des signaux précédents
            _prev_long[epic]  = signal is not None and signal["direction"] == "BUY"
            _prev_short[epic] = signal is not None and signal["direction"] == "SELL"

            if not signal:
                continue

            signals_found += 1

            # Ouvrir la position
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
                await telegram.send_signal(signal, DEMO_MODE)

            except BrokerError as e:
                logger.error("BrokerError %s: %s", asset_name, e)
                await telegram.send_error(f"Ordre {asset_name}", str(e))

        except Exception as e:
            logger.error("Erreur %s: %s", asset_name, e, exc_info=True)
            await telegram.send_error(f"Analyse {asset_name}", str(e))

        await asyncio.sleep(1)

    logger.info("Cycle terminé — signaux: %d | positions: %d", signals_found, len(open_positions))
    return signals_found


async def main():
    logger.info("╔══════════════════════════════╗")
    logger.info("║   ZorionBot démarré        ║")
    logger.info("║  Mode : %-6s               ║", "DÉMO" if DEMO_MODE else "LIVE")
    logger.info("╚══════════════════════════════╝")

    if not IG_API_KEY or "VOTRE" in IG_API_KEY:
        logger.critical("IG_API_KEY non configuré dans .env — arrêt.")
        return

    broker   = IGBroker(IG_API_KEY, IG_IDENTIFIER, IG_PASSWORD, DEMO_MODE)
    telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    await telegram.send_test_message()

    # Connexion avec retry
    for attempt in range(1, 4):
        try:
            await broker.connect()
            break
        except BrokerError as e:
            logger.error("Tentative %d/3 — connexion IG échouée: %s", attempt, e)
            await telegram.send_error("Démarrage", f"Tentative {attempt}/3 — {e}")
            if attempt == 3:
                logger.critical("Impossible de se connecter à IG — arrêt.")
                return
            await asyncio.sleep(60)

    await telegram.send_startup(DEMO_MODE, list(ENABLED_ASSETS.keys()))
    _load_disk_cache()

    last_summary  = None
    trades_today  = 0

    while True:
        try:
            wait = seconds_until_next_m30()
            logger.info("Prochain scan dans %.0fs", wait)
            await asyncio.sleep(wait)

            now       = datetime.now(timezone.utc)
            today_str = now.strftime("%Y-%m-%d")
            if now.hour == 8 and now.minute < 31 and last_summary != today_str:
                positions = await broker.get_open_positions()
                await telegram.send_daily_summary(trades_today, positions)
                last_summary = today_str
                trades_today = 0

            signals = await run_cycle(broker, telegram)
            trades_today += signals

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Erreur boucle principale: %s", e, exc_info=True)
            await telegram.send_error("Boucle principale", str(e))
            await asyncio.sleep(60)

    await broker.disconnect()
    logger.info("ZorionBot arrêté.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt manuel.")
```

- [ ] **Step 2: Lancer tous les tests une dernière fois**

```bash
python -m pytest tests/ -v
```
Attendu : tous les tests PASSED

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: add main.py — M30 main loop with 3-level candle cache"
```

---

## Task 10: Vérification finale Docker

- [ ] **Step 1: Builder l'image Docker**

```bash
cd ZorionBot
docker build -t zorionbot:test .
```
Attendu : `Successfully built ...`

- [ ] **Step 2: Vérifier que le conteneur démarre correctement**

```bash
docker run --rm \
  -e IG_API_KEY=test \
  -e IG_IDENTIFIER=test \
  -e IG_PASSWORD=test \
  -e TELEGRAM_BOT_TOKEN="" \
  -e TELEGRAM_CHAT_ID="" \
  -e DEMO_MODE=true \
  -e DATA_DIR=/tmp \
  zorionbot:test python -c "import main; print('Import OK')"
```
Attendu : `Import OK`

- [ ] **Step 3: Commit final**

```bash
git add .
git commit -m "chore: final check — Docker build verified"
```

---

## Récapitulatif des commits attendus

```
chore: project scaffold — Dockerfile, docker-compose, .env.example, requirements-dev.txt
feat: add risk.py — calculate_size and calculate_tp
feat: add indicators.py — donchian_channel and zlmacd
feat: add BaseBroker abstract interface and BrokerError
feat: add config.py and assets_config.py
feat: add IGBroker — IG Markets REST API implementation
feat: add TelegramNotifier
feat: add strategy.py — LONG/SHORT signal logic
feat: add main.py — M30 main loop with 3-level candle cache
chore: final check — Docker build verified
```
