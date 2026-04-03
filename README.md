# DonchianBot

Bot de trading autonome basé sur la stratégie **Donchian Channel V1.1 — Heiken Ashi** (traduction fidèle du Pine Script TradingView).

- Timeframe : **M30**
- Directions : **LONG et SHORT**
- Broker : **IG Markets** (architecture broker-agnostique)
- Déploiement : **Docker** (Raspberry Pi ou tout serveur Linux)
- Notifications : **Telegram**

---

## Stratégie

Le bot détecte des signaux de retournement en bordure du canal de Donchian. Les conditions utilisent les valeurs **Heiken Ashi** (HA) pour filtrer le bruit ; l'entrée et le stop restent sur les prix bruts.

**Signal LONG** — toutes les conditions doivent être vraies :

| Condition | Description |
|-----------|-------------|
| Touche la bande basse (HA) | haLow d'une des 3 dernières bougies ≤ bande basse |
| Bougie HA haussière | haClose > haOpen sur la bougie signal |
| Breakout HA | haClose dépasse le haHigh de la bougie précédente |
| Zone d'achat (HA) | haOpen se situe sous le premier quartile (limitLow) |
| ZL-MACD < 0 | Contexte baissier — filtre retournement |

**Signal SHORT** : symétrique (bande haute, bougie HA baissière, ZL-MACD > 0).

**Gestion des positions :**
- Entry = high[-2] (LONG) ou low[-2] (SHORT)
- Stop Loss = min/max des 2 dernières bougies
- Take Profit = entry ± (distance SL × R:R ratio)
- Taille de position = montant risqué ÷ (distance SL × point value)

---

## Prérequis

- Docker et Docker Compose installés
- Un compte IG Markets (démo ou réel) avec accès API
- Un bot Telegram (optionnel mais recommandé)

---

## Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/Zorion83/DonchianBot.git
cd DonchianBot
```

### 2. Créer le fichier de configuration

```bash
# Créer le répertoire de données (à adapter selon votre machine)
sudo mkdir -p /srv/data/donchianbot

# Copier le fichier de config exemple
cp .env.example /srv/data/donchianbot/.env
```

### 3. Remplir le fichier `.env`

Éditez `/srv/data/donchianbot/.env` :

```bash
nano /srv/data/donchianbot/.env
```

#### Section BROKER — IG Markets

```env
BROKER=ig

# Clé API : Mon Compte IG > Paramètres > API
IG_API_KEY=votre_cle_api

# Votre identifiant de connexion IG
IG_IDENTIFIER=votre_identifiant

# Votre mot de passe IG
IG_PASSWORD=votre_mot_de_passe

# true = compte démo, false = compte réel
# ⚠️ Toujours commencer par true
DEMO_MODE=true
```

#### Section TELEGRAM — Notifications

```env
# Token obtenu via @BotFather sur Telegram (/newbot)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# Votre Chat ID — obtenu via @userinfobot ou @RawDataBot
TELEGRAM_CHAT_ID=123456789
```

> Si vous ne souhaitez pas utiliser Telegram, laissez ces champs vides. Le bot fonctionnera sans envoyer de notifications.

#### Section STRATÉGIE

```env
# Période du canal de Donchian (recommandé : 100)
DONCHIAN_LENGTH=100

# Bougies historiques chargées au démarrage (recommandé : 500)
LOOKBACK_CANDLES=500
```

#### Section RISQUE

```env
# Montant risqué par trade en devise du compte (ex: 50€)
RISK_AMOUNT=50.0

# Valeur d'un point (valeur par défaut, surchargeable par actif)
POINT_VALUE=1.0

# Ratio R:R pour le Take Profit (2.0 = TP à 2× la distance du SL)
RR_RATIO=2.0
```

### 4. Configurer les actifs

Éditez `app/assets_config.py` pour définir les marchés à surveiller :

```python
ASSETS = {
    "DAX": {
        "symbol":      "IX.D.DAX.IFMM.IP",  # Epic IG Markets
        "point_value": 1.0,                  # Valeur d'un point
        "rr_ratio":    2.0,                  # Ratio R:R (override .env)
        "enabled":     True,
    },
    "NAS100": {
        "symbol":      "IX.D.NASDAQ.IFD.IP",
        "point_value": 1.0,
        "rr_ratio":    2.0,
        "enabled":     True,
    },
    # Ajoutez vos actifs ici...
}
```

**Trouver l'epic d'un instrument IG :**
Dans l'interface IG, cliquez sur un marché → **Informations** → champ **Epic**.

**Priorité des paramètres :**
Si `point_value` ou `rr_ratio` est défini dans l'actif, il prend la priorité sur la valeur globale du `.env`. Sinon, la valeur globale est utilisée.

### 5. Lancer le bot

```bash
docker compose up -d
```

Le bot démarre, se connecte à IG Markets, charge les bougies historiques et attend la prochaine clôture M30.

---

## Structure des fichiers

```
DonchianBot/
├── app/
│   ├── main.py               # Boucle principale M30
│   ├── config.py             # Lecture des variables .env
│   ├── assets_config.py      # ⚙️ Liste des actifs à remplir
│   ├── indicators.py         # Donchian Channel + ZL-MACD + Heiken Ashi
│   ├── strategy.py           # Logique des signaux LONG/SHORT
│   ├── risk.py               # Calcul taille de position et TP
│   ├── brokers/
│   │   ├── base_broker.py    # Interface abstraite broker
│   │   └── ig_broker.py      # Implémentation IG Markets
│   ├── telegram_notifier.py  # Notifications Telegram
│   └── requirements.txt
├── tests/                    # Suite de tests (35 tests)
├── Dockerfile
├── docker-compose.yml
├── .env.example              # ⚙️ Modèle de configuration
└── .gitignore
```

---

## Commandes utiles

```bash
# Démarrer le bot
docker compose up -d

# Voir les logs en temps réel
docker compose logs -f

# Arrêter le bot
docker compose down

# Redémarrer après modification de assets_config.py
docker compose restart

# Reconstruire l'image (après mise à jour du code)
docker compose up -d --build
```

---

## Notifications Telegram

Le bot envoie automatiquement :

| Événement | Message |
|-----------|---------|
| Démarrage | Mode (démo/live) + liste des actifs actifs |
| Signal | Direction, actif, entry/SL/TP, quantité |
| Erreur broker | Message d'erreur détaillé |
| Résumé quotidien | Chaque jour à 08h00 UTC — nombre de trades + positions ouvertes |

---

## Fonctionnement du cache de bougies

Au démarrage, le bot charge `LOOKBACK_CANDLES` bougies M30 depuis l'API IG et les sauvegarde sur disque (`/app/data/candle_cache.json`). À chaque cycle suivant, seules 3 nouvelles bougies sont demandées — ce qui minimise l'utilisation de l'API et évite les erreurs de quota.

En cas de quota dépassé (erreur 403), l'actif est analysé depuis le cache existant et un warning est logué.

---

## Déploiement sur Raspberry Pi

Le Dockerfile est configuré pour l'architecture ARM64 :

```bash
# Sur la Raspi — cloner et lancer
git clone https://github.com/Zorion83/DonchianBot.git
cd DonchianBot

sudo mkdir -p /srv/data/donchianbot
sudo cp .env.example /srv/data/donchianbot/.env
# Remplir le .env et assets_config.py, puis :
docker compose up -d
```

Le bot tourne en continu avec `restart: unless-stopped` et effectue une rotation automatique des logs (max 10 Mo × 3 fichiers).

---

## Tests

```bash
# Installer les dépendances de dev
pip install -r requirements-dev.txt

# Lancer les tests
pytest tests/ -v
```

35 tests couvrent les indicateurs (dont Heiken Ashi), le calcul du risque, la stratégie et les notifications.

---

## ⚠️ Avertissement

Ce bot est fourni à titre éducatif. Le trading sur CFD et instruments financiers comporte un risque de perte en capital. Testez toujours en mode démo (`DEMO_MODE=true`) avant de passer sur un compte réel.
