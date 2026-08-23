# DonchianBot — Document de transfert vers nouvelle machine

> ⚠️ **Renommage du projet en cours (2026-08)** : `DonchianBot` devient `ZorionBot`. Ce document décrit encore l'infrastructure réelle du Pi sous l'ancien nom (`donchianbot`, `/srv/data/donchianbot`) — ces chemins ne changeront qu'à la migration planifiée pour septembre 2026. Voir [`docs/PI_MIGRATION_ZORIONBOT.md`](./PI_MIGRATION_ZORIONBOT.md).

> **Usage** : Ce document est destiné à Claude Code pour reconfigurer l'environnement de
> développement sur une nouvelle machine Mac, à partir d'un clone Git du projet.
> Il couvre : SSH, déploiement Raspi, règles critiques, état du code.

---

## 1. Vue d'ensemble du projet

**DonchianBot** est un bot de trading algorithmique tournant en continu sur un Raspberry Pi 5.
Il analyse SPY, QQQ et BTC/USD sur des bougies M30 via la stratégie Donchian Channel V1.1
(Heiken Ashi) et passe des ordres via l'API Alpaca Markets (paper trading actuellement).

- **Broker** : Alpaca Markets (paper trading)
- **Timeframe** : M30 (30 minutes)
- **Assets** : SPY, QQQ (stocks US), BTC/USD (crypto)
- **Notifications** : Telegram
- **Infrastructure** : Raspberry Pi 5, Docker, debian trixie (aarch64)

---

## 2. Structure des machines

### Machine de développement (Mac)

```
~/.ssh/config                          ← entrée SSH raspi-home
~/Documents/Developpement/Claude.Cowork/Algo_B&G/DonchianBot/   ← projet
```

> **Note chemin** : Le `&` dans `Algo_B&G` doit toujours être entre guillemets dans le shell.
> Utiliser : `"/Users/<user>/Documents/Developpement/Claude.Cowork/Algo_B&G/DonchianBot/"`

### Raspberry Pi 5

```
OS        : Debian GNU/Linux 13 (trixie) — aarch64
Docker    : 26.1.5
Compose   : 2.26.1
User      : zorion
IP locale : 192.168.1.197
Projet    : ~/DonchianBot/
Data      : /srv/data/donchianbot/   ← seul volume monté dans Docker
```

---

## 3. Configuration SSH (à créer sur la nouvelle machine)

Ajouter dans `~/.ssh/config` :

```
Host raspi-home
  HostName 192.168.1.197
  User zorion
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
```

Copier la clé SSH publique sur la Raspi :

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub zorion@192.168.1.197
```

Test :

```bash
ssh raspi-home "echo OK"
```

---

## 4. Structure du projet

```
DonchianBot/
├── Dockerfile                     # image arm64 python:3.11.9-slim
├── docker-compose.yml             # build:. + volume /srv/data/donchianbot
├── .env.example                   # template variables d'environnement
├── .gitignore
├── requirements-dev.txt
├── app/
│   ├── main.py                    # boucle principale, gestion cycles M30
│   ├── strategy.py                # logique signal LONG/SHORT (Donchian + HA + ZLMACD)
│   ├── indicators.py              # donchian_channel(), zlmacd(), heiken_ashi()
│   ├── risk.py                    # calculate_size(), calculate_tp()
│   ├── assets_config.py           # ASSETS dict (SPY, QQQ, BTC/USD)
│   ├── config.py                  # lecture variables d'env
│   ├── telegram_notifier.py       # notifications Telegram
│   ├── requirements.txt
│   └── brokers/
│       ├── base_broker.py         # interface abstraite BaseBroker
│       ├── alpaca_broker.py       # implémentation Alpaca Markets
│       └── ig_broker.py           # implémentation IG (non utilisée actuellement)
├── tests/
└── docs/
    └── TRANSFER.md                # ce fichier
```

---

## 5. Variables d'environnement

Le fichier `.env` **n'est pas versionné**. Il est stocké sur la Raspi à :
```
/srv/data/donchianbot/.env
```

Variables requises (voir `.env.example` pour la documentation complète) :

```env
# Alpaca Markets
ALPACA_API_KEY=PK...
ALPACA_API_SECRET=...
DEMO_MODE=true                  # true = paper trading

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Stratégie
DONCHIAN_LENGTH=100
LOOKBACK_CANDLES=500

# Risque
RISK_PCT=0.005                  # 0.5% du solde par trade
POINT_VALUE=1.0
RR_RATIO=2.0

# Logs
LOG_LEVEL=INFO
DATA_DIR=/app/data              # ne pas modifier
```

Pour récupérer le `.env` actuel depuis la Raspi :

```bash
scp raspi-home:/srv/data/donchianbot/.env "/chemin/local/.env.raspi"
```

---

## 6. ⚠️ Règle critique de déploiement

> **Le code est baked dans l'image Docker au moment du `build`.**
> Le seul dossier monté en volume est `/srv/data/donchianbot` (données persistantes).

### ❌ NE JAMAIS faire pour appliquer du code :
```bash
docker compose restart      # recharge le container mais PAS le code
docker compose up -d        # idem, utilise l'image existante
```

### ✅ TOUJOURS faire après modification du code :
```bash
# Sur la Raspi (ou via SSH) :
docker compose up -d --build
```

### Workflow complet de déploiement depuis le Mac :

```bash
# 1. Synchroniser les fichiers modifiés
rsync -av \
  "/Users/<user>/Documents/Developpement/Claude.Cowork/Algo_B&G/DonchianBot/app/main.py" \
  raspi-home:~/DonchianBot/app/main.py

# 2. Rebuilder l'image ET redémarrer le container
ssh raspi-home "cd ~/DonchianBot && docker compose up -d --build"

# 3. Vérifier les logs
ssh raspi-home "docker logs donchianbot --tail=20"
```

---

## 7. État actuel du code (fixes appliqués)

### Contexte : historique des erreurs Alpaca 422

Depuis le lancement du bot, toutes les tentatives d'ordre échouaient avec `HTTP 422`.
Les causes et fixes sont documentés ci-dessous.

---

### Fix 1 — Crypto : `order_class: otoco` non supporté

**Symptôme** : `"crypto orders not allowed for advanced order_class: otoco"`

**Cause** : Alpaca ne supporte pas les bracket orders pour les cryptos.

**Fix dans `app/brokers/alpaca_broker.py`** :
- Crypto : `order_class: "simple"`, `time_in_force: "gtc"`, qty fractionnaire (`round(size, 6)`)
- Stocks : `order_class: "simple"`, `time_in_force: "day"`, qty entière (`math.floor(size)`)

Les SL/TP ne sont **pas attachés à l'ordre** — ils sont gérés par la boucle principale
(TP/SL monitoring dans `main.py`, toutes les 30 minutes, via `broker.close_position()`).

---

### Fix 2 — Stocks : bracket orders rejetés

**Symptôme** : `"fractional orders must be DAY orders"` sur SPY/QQQ

**Cause** : Alpaca Paper Trading rejette les bracket orders (GTC ou non) pour les actifs
fractionnables. La quantité calculée par `calculate_size()` était passée sans `math.floor()`.

**Fix** : Même fix que ci-dessus (simple order + `math.floor`).

---

### Fix 3 — Gate horaires de marché US

**Symptôme** : Erreur 422 sur SPY/QQQ à 08:30 UTC (04:30 EDT = pre-market) et 20:00 UTC
(16:00 EDT = après fermeture). Alpaca refuse les orders "day" hors heures de marché.

**Fix dans `app/main.py`** :

```python
def _is_stock_market_open() -> bool:
    """Return True si US regular market hours actives (lun-ven, 13:30–20:00 UTC)."""
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:   # samedi=5, dimanche=6
        return False
    market_open  = now.replace(hour=13, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=20, minute=0,  second=0, microsecond=0)
    return market_open <= now < market_close
```

Le gate est dans `run_cycle()`, après `analyse_asset()` :
- Si signal détecté ET asset = stock ET marché fermé → log "hors-marché" + continuer
- Les flags anti-doublon (`_prev_long`, `_prev_short`) **ne sont pas modifiés**
  → le signal peut réessayer au prochain cycle M30

---

### Fix 4 — Anti-doublon

**Problème** : `_prev_long[epic]` était mis à `True` **avant** la tentative d'ordre.
Si l'ordre échouait (422, hors-marché…), le signal était bloqué au cycle suivant.

**Fix** : L'update des flags anti-doublon est maintenant après le gate horaire et
**avant** la tentative d'ordre (pas après le succès — cela reste voulu pour éviter
de re-déclencher le même signal si l'ordre passe mais la position s'ouvre lentement).

Flux dans `run_cycle()` :
```
analyse_asset()
  → Pas de signal           → _prev_long/short = False  → continue
  → Signal + hors-marché   → rien (flags inchangés)     → continue
  → Signal + marché ouvert → _prev_long/short = True    → tenter l'ordre
      → Succès → signals_found += 1 + cache + Telegram
      → Échec  → logger.error + telegram.send_error
```

---

### Fix 5 — Compteur `signals_found`

**Problème** : `signals_found += 1` était exécuté même si l'ordre échouait.

**Fix** : `signals_found += 1` est maintenant à l'intérieur du `try`, après
`await broker.open_long/open_short()`. Il n'est incrémenté que sur succès.

---

### Fix 6 — TP/SL monitoring (tous actifs)

Puisque les ordres sont "simple" sans SL/TP attachés, la boucle surveille les positions
ouvertes à chaque cycle M30 :

```python
# Dans run_cycle() — pour chaque position ouverte :
if direction == "BUY":
    hit_tp = current_price >= tp_price
    hit_sl = current_price <= sl_price
else:
    hit_tp = current_price <= tp_price
    hit_sl = current_price >= sl_price

if hit_tp or hit_sl:
    await broker.close_position(epic)   # DELETE /v2/positions/{symbol}
```

Les niveaux SL/TP sont stockés dans `_signal_cache` (persisté dans `bot_state.json`).

---

## 8. Procédure de transfert complète

### Sur l'ancienne machine (avant de changer)

```bash
# 1. Récupérer le .env (contient les vraies clés API)
scp raspi-home:/srv/data/donchianbot/.env ~/Desktop/.env.donchianbot.backup

# 2. Vérifier que tout est commité sur Git
cd "/Users/<user>/Documents/Developpement/Claude.Cowork/Algo_B&G/DonchianBot"
git status
git log --oneline -5
```

### Sur la nouvelle machine

```bash
# 1. Cloner le projet
git clone <url-du-repo> "/chemin/vers/DonchianBot"
cd "/chemin/vers/DonchianBot"

# 2. Configurer SSH
cat >> ~/.ssh/config << 'EOF'
Host raspi-home
  HostName 192.168.1.197
  User zorion
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
EOF

# Générer une clé si nécessaire
ssh-keygen -t ed25519 -C "nouvelle-machine"
ssh-copy-id -i ~/.ssh/id_ed25519.pub zorion@192.168.1.197

# Tester
ssh raspi-home "docker ps"

# 3. Vérifier l'état du bot
ssh raspi-home "docker logs donchianbot --tail=30"

# 4. Pour modifier le code et déployer (TOUJOURS --build)
rsync -av app/ raspi-home:~/DonchianBot/app/
ssh raspi-home "cd ~/DonchianBot && docker compose up -d --build"
```

---

## 9. Commandes utiles (référence rapide)

```bash
# Logs en temps réel
ssh raspi-home "docker logs donchianbot --follow"

# Logs filtrés (erreurs + signaux)
ssh raspi-home "docker logs donchianbot 2>&1 | grep -E '(ERROR|signal|BrokerError|hors-marché)'"

# Vérifier ce qui tourne DANS le container (code actuel)
ssh raspi-home "docker exec donchianbot grep -n '_is_stock_market_open' /app/main.py"

# État du bot (depuis Telegram)
# Envoyer /status au bot Telegram

# Données persistantes
ssh raspi-home "ls -la /srv/data/donchianbot/"
ssh raspi-home "cat /srv/data/donchianbot/bot_state.json"

# Redémarrer proprement
ssh raspi-home "cd ~/DonchianBot && docker compose down && docker compose up -d --build"

# Voir les ressources
ssh raspi-home "docker stats donchianbot --no-stream"
```

---

## 10. Points d'attention / TODOs connus

- **Jours fériés US** : La gate `_is_stock_market_open()` vérifie lun-ven + horaires UTC
  mais **pas les jours fériés US** (Thanksgiving, Christmas…). Alpaca rejettera les ordres
  ces jours-là avec la même erreur 422. À corriger si nécessaire via l'API Alpaca Calendar.

- **Alpaca Paper Trading seulement** : Tant que `DEMO_MODE=true`, aucun argent réel.
  Avant de passer en live, vérifier `DEMO_MODE=false` + clés API du compte réel.

- **Tailscale** : Pour accéder à la Raspi hors réseau local (depuis un autre réseau ou téléphone),
  installer Tailscale sur la Raspi et sur la nouvelle machine.
  ```bash
  # Sur la Raspi
  curl -fsSL https://tailscale.com/install.sh | sh
  sudo tailscale up
  tailscale ip -4   # → IP du style 100.x.x.x
  ```
  Puis mettre à jour `~/.ssh/config` avec l'IP Tailscale.
