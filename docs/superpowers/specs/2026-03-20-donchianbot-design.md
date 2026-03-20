# DonchianBot — Design Spec
**Date :** 2026-03-20
**Statut :** Approuvé

---

## Contexte

Bot de trading autonome basé sur la stratégie Donchian V1.1 (Pine Script TradingView).
Tourne en parallèle du SwingBot existant sur Raspberry Pi, dans un conteneur Docker indépendant.

**Contraintes :**
- Ne pas modifier le dossier SwingBot
- Broker-agnostique (config vierge commentée)
- Telegram dédié (config vierge commentée)
- Timeframe : M30
- Directions : LONG et SHORT
- Déploiement final sur GitHub

---

## Structure des fichiers

```
Algo_B&G/
└── DonchianBot/
    ├── app/
    │   ├── main.py               # Boucle principale M30
    │   ├── config.py             # Lecture des variables .env
    │   ├── assets_config.py      # Liste des actifs (à remplir par l'utilisateur)
    │   ├── indicators.py         # Calculs Donchian Channel + ZL-MACD
    │   ├── strategy.py           # Logique des signaux LONG/SHORT
    │   ├── risk.py               # Calcul taille de position (logique pure)
    │   ├── brokers/
    │   │   ├── __init__.py
    │   │   ├── base_broker.py    # Classe abstraite (contrat broker)
    │   │   └── ig_broker.py      # Implémentation IG Markets
    │   ├── telegram_notifier.py  # Notifications Telegram
    │   └── requirements.txt
    ├── Dockerfile
    ├── docker-compose.yml
    ├── .env.example              # Config vierge commentée
    └── .gitignore
```

---

## Architecture & Flux de données

```
main.py (boucle M30)
  │
  ├─► config.py          → lit le .env
  ├─► assets_config.py   → liste des actifs activés
  │
  ├─► IGBroker           → fetch bougies M30 (cache 3 niveaux)
  │     (implémente BaseBroker)
  │
  ├─► indicators.py      → Donchian Channel + ZL-MACD
  │
  ├─► strategy.py        → signal LONG / SHORT / None
  │
  ├─► risk.py            → calcule qty (taille de position)
  │
  ├─► IGBroker           → open_long() ou open_short()
  │                         lève BrokerError si rejet
  │
  └─► TelegramNotifier   → notification
```

---

## Composants

### `brokers/base_broker.py`
Classe abstraite définissant le contrat :
- `connect()` / `disconnect()`
- `get_candles(symbol, count, timeframe)` → `List[dict]`
- `get_account_balance()` → `float`
- `get_open_positions()` → `List[dict]`
- `open_long(symbol, size, sl, tp, **kwargs)` → `None` (lève `BrokerError` si échec)
- `open_short(symbol, size, sl, tp, **kwargs)` → `None` (lève `BrokerError` si échec)

**Note :** `calculate_size` n'est PAS dans `BaseBroker` — c'est du calcul pur, sans appel broker.
Il est dans `risk.py`.

**Structure minimale du dict position** (retourné par `get_open_positions`) :
```python
{
    "epic":      str,   # identifiant de l'instrument (ex: "IX.D.DAX.IFMM.IP")
    "direction": str,   # "BUY" ou "SELL"
    "size":      float, # taille de la position
    "deal_id":   str,   # identifiant unique de la position
}
```

**Exception `BrokerError`** : définie dans `brokers/base_broker.py`, inclut un message descriptif.
`main.py` la capture, logue et envoie une alerte Telegram avec le message d'erreur.

### `brokers/ig_broker.py`
Implémente `BaseBroker` pour IG Markets REST API.
Patterns : httpx async, sessions CST/X-SECURITY-TOKEN.
Code indépendant du SwingBot (pas de copie, même logique réécrite).

### `risk.py`
Module utilitaire de calcul pur, sans dépendance broker :
```python
def calculate_size(risk_amount: float, entry: float, sl: float, point_value: float) -> float:
    distance = abs(entry - sl)
    if distance == 0:
        return 0.0
    return risk_amount / (distance * point_value)

def calculate_tp(entry: float, sl: float, rr_ratio: float, direction: str) -> float:
    distance = abs(entry - sl)
    if direction == "BUY":
        return entry + distance * rr_ratio
    return entry - distance * rr_ratio
```

### `indicators.py`
Deux fonctions pures (sans état).

**Convention d'indexation des bougies :**
`candles[-1]` = bougie signal (dernière bougie fermée)
`candles[-2]` = bougie précédente
`candles[-3]` = ante-pénultième

```python
def donchian_channel(highs: list, lows: list, length: int) -> tuple:
    upper     = max(highs[-length:])
    lower     = min(lows[-length:])
    basis     = (upper + lower) / 2
    limitHigh = upper - (upper - basis) / 2
    limitLow  = lower + (basis - lower) / 2
    return upper, lower, basis, limitHigh, limitLow

def zlmacd(closes: list, fast: int = 12, slow: int = 26) -> float:
    """
    Zero Lag MACD = DEMA(fast) - DEMA(slow)
    DEMA(n) = 2 * EMA(close, n) - EMA(EMA(close, n), n)

    NOTE : Seule la valeur de la ligne MACD est retournée.
    La signal line et l'histogramme sont intentionnellement omis —
    les conditions de la stratégie utilisent uniquement zlmacd > 0 / < 0.
    """
    ema1     = _ema_series(closes, fast)
    ema2     = _ema_series(ema1, fast)
    demaFast = 2 * ema1[-1] - ema2[-1]

    emas1    = _ema_series(closes, slow)
    emas2    = _ema_series(emas1, slow)
    demaSlow = 2 * emas1[-1] - emas2[-1]

    return demaFast - demaSlow
```

**Nombre minimum de bougies requis** :
- MACD slow = 26, appliqué deux fois → min 52 bougies pour le ZL-MACD
- Donchian length = 100 par défaut
- Buffer de sécurité : `LOOKBACK_CANDLES` doit être ≥ `DONCHIAN_LENGTH + 60`
- Valeur par défaut recommandée : `LOOKBACK_CANDLES=500`

### `strategy.py`

**Signal LONG** — toutes conditions vraies :

| Condition | Description |
|-----------|-------------|
| `any(l <= lower for l in lows[-3:])` | Touche le bas du canal (3 dernières bougies) |
| `closes[-1] > opens[-1]` | Bougie signal haussière |
| `closes[-1] > highs[-2]` | Close de la bougie signal dépasse le high de la précédente |
| `opens[-1] < limitLow` | Ouverture de la bougie signal en zone achat |
| `zlmacd < 0` | Contexte baissier (filtre retournement) |
| `not prev_long_signal` | Pas de signal LONG à la bougie précédente (anti-doublon) |

**Signal SHORT** — symétrique :

| Condition | Description |
|-----------|-------------|
| `any(h >= upper for h in highs[-3:])` | Touche le haut du canal (3 dernières bougies) |
| `closes[-1] < opens[-1]` | Bougie signal baissière |
| `closes[-1] < lows[-2]` | Close perce le low de la précédente |
| `opens[-1] > limitHigh` | Ouverture en zone vente |
| `zlmacd > 0` | Contexte haussier (filtre retournement) |
| `not prev_short_signal` | Anti-doublon |

**Prix d'exécution :**
```
LONG  : entry = highs[-2],  SL = min(lows[-1], lows[-2])
SHORT : entry = lows[-2],   SL = max(highs[-1], highs[-2])
TP    = entry ± (|entry - SL| × RR_RATIO)
qty   = risk.calculate_size(RISK_AMOUNT, entry, SL, POINT_VALUE)
tp    = risk.calculate_tp(entry, SL, RR_RATIO, direction)
```
`tp_price` est calculé via `risk.calculate_tp` — la stratégie ne duplique pas cette arithmétique.

Retourne un dict signal ou `None` :
```python
{
    "direction":   "BUY" | "SELL",
    "entry_price": float,
    "sl_price":    float,
    "tp_price":    float,
    "qty":         float,
    "asset_name":  str,
    "symbol":      str,
}
```

### `main.py`
- Boucle `while True` calée sur la fermeture des bougies M30 (`seconds_until_next_m30()`)
- Cache bougies 3 niveaux (disque → rattrapage → incrémental)
- Anti-collision : skip si une position est déjà ouverte sur cet actif (comparaison par `epic`)
- **Résumé quotidien Telegram** : déclenché par comparaison de timestamp dans la boucle principale — si `now.hour == 8 and now.minute < 31 and last_summary != today_str`, émettre le résumé et mettre à jour `last_summary`
- **Démarrage sans cache (cold start)** : si le fetch initial échoue (erreur API, credentials incorrects), le bot logue l'erreur, envoie une alerte Telegram et attend 60s avant de réessayer (max 3 tentatives, puis arrêt avec log CRITICAL)

### `config.py`
Toutes les variables lues depuis `.env` via `os.environ.get()`.

### `assets_config.py`
Schema du dict par actif :
```python
ASSETS = {
    "DAX": {
        "symbol":      str,   # Epic IG Markets (ex: "IX.D.DAX.IFMM.IP")
        "point_value": float, # Valeur d'un point (ex: 1.0 ou 25.0 pour DAX Mini)
        "rr_ratio":    float, # Ratio R:R pour le TP (ex: 2.0)
        "enabled":     bool,  # True pour activer l'actif
    },
    # ...
}

ENABLED_ASSETS = {k: v for k, v in ASSETS.items() if v.get("enabled", False)}
```

Note : `RISK_AMOUNT` et `DONCHIAN_LENGTH` sont globaux (dans `.env`), pas par actif.
`POINT_VALUE` peut être surchargé par actif via ce dict. Règle de priorité : si `point_value` est présent dans le dict actif, il prend la priorité sur la valeur globale `POINT_VALUE` du `.env` ; sinon la valeur globale est utilisée.

### `.env.example`
Fichier vierge entièrement commenté, structuré en 5 sections :
- Broker (type + credentials IG)
- Telegram (token + chat_id)
- Stratégie (longueur Donchian, lookback)
- Risque (montant, point value global, R:R global)
- Logs

---

## Docker

### `Dockerfile`
```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt .          # requirements.txt est dans app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

CMD ["python", "-u", "main.py"]
```

### `docker-compose.yml`
```yaml
services:
  donchianbot:
    container_name: donchianbot
    build: .
    restart: unless-stopped
    env_file:
      - /srv/data/donchianbot/.env
    volumes:
      - /srv/data/donchianbot:/app/data
    environment:
      - DATA_DIR=/app/data
```

Données persistées dans `/srv/data/donchianbot/` — **indépendant du SwingBot** (`/srv/data/swingbot/`).

---

## Gestion des erreurs

| Situation | Comportement |
|-----------|-------------|
| Quota API dépassé | Warning log, actif skippé, cache existant utilisé |
| Connexion broker échouée au démarrage | Alerte Telegram + retry toutes les 60s (max 3) puis arrêt CRITICAL |
| `BrokerError` sur `open_long`/`open_short` | Log + alerte Telegram avec message d'erreur, les autres actifs continuent |
| Erreur inattendue par actif | Log + alerte Telegram, les autres actifs continuent |
| Cache disque absent au premier démarrage | Fetch complet `LOOKBACK_CANDLES` bougies via API |

---

## `.gitignore`
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

---

## Déploiement
1. Créer `/srv/data/donchianbot/.env` sur la raspi (à partir de `.env.example`)
2. `docker compose up -d` depuis `DonchianBot/`
3. Les deux bots tournent indépendamment, aucun fichier partagé

---

## GitHub
Repository dédié à créer pour `DonchianBot/` une fois le code finalisé.
`.gitignore` inclut `.env`, `data/`, `logs/` et fichiers Python compilés.
