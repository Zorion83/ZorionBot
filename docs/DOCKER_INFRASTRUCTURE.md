# Infrastructure Docker — Raspberry Pi 5

> **Note importante** : Docker tourne sur le **Raspberry Pi**, pas sur le Mac.
> Le Mac est uniquement la machine de développement (éditeur de code + déploiement via SSH/rsync).
> Ce document décrit l'infrastructure à reproduire si tu changes de Raspi.

---

## Vue d'ensemble

Le Raspi héberge **4 containers Docker** qui forment un écosystème complet :

```
Raspberry Pi 5
│
├── caddy          — Reverse proxy HTTPS (accès public)
├── homepage       — Dashboard de monitoring (interface web)
├── donchianbot    — Bot de trading Donchian (ce projet)
└── swingbot       — Bot de trading Swing (autre projet)

Données persistantes → /srv/data/<nom_service>/
```

---

## Structure des répertoires

```
/srv/
└── data/
    ├── caddy/
    │   ├── Caddyfile      ← configuration du reverse proxy
    │   ├── config/        ← config interne Caddy
    │   └── data/          ← certificats TLS (auto-générés)
    │
    ├── homepage/
    │   ├── services.yaml  ← tuiles de services affichés
    │   ├── widgets.yaml   ← widgets (météo, date…)
    │   ├── settings.yaml  ← apparence / layout
    │   ├── bookmarks.yaml
    │   ├── docker.yaml
    │   └── logs/
    │
    ├── donchianbot/
    │   ├── .env           ← clés API (Alpaca + Telegram) ⚠️ non versionné
    │   ├── bot_state.json ← état du bot (last_summary, signal_cache)
    │   ├── candle_cache.json ← cache des bougies (~150 KB)
    │   └── donchianbot.log   ← logs rotatifs (max 3 × 10 MB)
    │
    └── swingbot/
        ├── active_trades.json
        ├── candle_cache.json
        └── swing_bot.log

~/
├── DonchianBot/   ← code source (cloné depuis GitHub)
├── swingbot/      ← code source SwingBot
└── ...
```

---

## Container 1 — Caddy (reverse proxy)

**Image** : `caddy:2` (officielle)
**Rôle** : Reçoit les requêtes HTTP/HTTPS entrantes et les redirige vers les bons containers.
Gère automatiquement les certificats TLS via Let's Encrypt.

**Ports exposés** :
- `80` → HTTP (redirige vers HTTPS)
- `443` → HTTPS

**Volume** : `/srv/data/caddy` → config + certificats

---

## Container 2 — Homepage (dashboard)

**Image** : `ghcr.io/gethomepage/homepage:latest`
**Rôle** : Interface web de monitoring — affiche l'état des services, liens rapides, widgets.
Accessible via le navigateur (protégé par Caddy).

**Volume** : `/srv/data/homepage` → fichiers de configuration YAML

---

## Container 3 — DonchianBot ⬅ ce projet

**Image** : construite localement depuis le `Dockerfile` du projet
**Rôle** : Bot de trading algorithmique (stratégie Donchian Channel V1.1, M30)

### Dockerfile

```dockerfile
FROM --platform=linux/arm64 python:3.11.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

RUN useradd -r -u 1000 botuser && chown -R botuser /app
USER botuser

CMD ["python", "-u", "main.py"]
```

> ⚠️ `--platform=linux/arm64` : l'image est compilée pour l'architecture ARM du Raspi.
> Si tu rebuildes depuis un Mac Intel (x86), ajoute `--platform linux/arm64` ou utilise
> le `buildx` Docker. En pratique : toujours builder **sur le Raspi** via `docker compose up -d --build`.

### docker-compose.yml

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
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

**Points clés** :
- `restart: unless-stopped` → redémarre automatiquement après un crash ou un reboot
- `env_file` → les clés API ne sont **jamais** dans le code, seulement dans `/srv/data/donchianbot/.env`
- `volumes` → seul `/srv/data/donchianbot` est persistant ; le code est baked dans l'image
- **Logs JSON** → limités à 3 fichiers × 10 MB (30 MB max)

### Principe fondamental du déploiement

```
❌ docker compose restart     → recharge le container SANS le nouveau code
✅ docker compose up -d --build  → rebuild l'image ET redémarre
```

---

## Container 4 — SwingBot

**Image** : construite localement
**Rôle** : Bot de trading Swing (projet séparé, même infrastructure)
**Volume** : `/srv/data/swingbot`

---

## Commandes utiles (depuis le Mac via SSH)

```bash
# Voir tous les containers
ssh raspi-home "docker ps -a"

# Logs d'un container en temps réel
ssh raspi-home "docker logs donchianbot --follow"

# Redéployer DonchianBot après modification du code
rsync -av app/ raspi-home:~/DonchianBot/app/
ssh raspi-home "cd ~/DonchianBot && docker compose up -d --build"

# Redémarrer sans rebuilder (ex: après modif du .env uniquement)
ssh raspi-home "cd ~/DonchianBot && docker compose restart"

# Voir la consommation des ressources
ssh raspi-home "docker stats --no-stream"

# Voir les volumes utilisés
ssh raspi-home "docker system df"
```

---

## Procédure de duplication sur un nouveau Raspi

### 1. Prérequis système

```bash
# Installer Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # pour éviter sudo à chaque commande
# Se déconnecter / reconnecter pour appliquer

# Vérifier
docker --version
docker compose version
```

### 2. Créer la structure de données

```bash
sudo mkdir -p /srv/data/donchianbot
sudo mkdir -p /srv/data/caddy/{config,data}
sudo mkdir -p /srv/data/homepage/logs
sudo mkdir -p /srv/data/swingbot
sudo chown -R zorion:zorion /srv/data
```

### 3. Transférer les données persistantes depuis l'ancien Raspi

```bash
# Depuis le Mac — copier les données de l'ancien vers le nouveau Raspi
# (remplacer NOUVEAU_RASPI_IP par l'IP du nouveau Raspi)

# DonchianBot
ssh raspi-home "tar -czf - /srv/data/donchianbot" | ssh zorion@NOUVEAU_RASPI_IP "tar -xzf - -C /"

# Homepage
ssh raspi-home "tar -czf - /srv/data/homepage" | ssh zorion@NOUVEAU_RASPI_IP "tar -xzf - -C /"

# Caddy (certificats + config)
ssh raspi-home "tar -czf - /srv/data/caddy" | ssh zorion@NOUVEAU_RASPI_IP "tar -xzf - -C /"
```

> ⚠️ Si l'IP ou le domaine change, les certificats Caddy devront être régénérés.
> Supprimer `/srv/data/caddy/data` sur le nouveau Raspi pour forcer le renouvellement.

### 4. Cloner et déployer DonchianBot

```bash
# Sur le nouveau Raspi
git clone https://github.com/Zorion83/DonchianBot.git ~/DonchianBot
cd ~/DonchianBot
docker compose up -d --build
```

### 5. Vérifier

```bash
docker ps -a
docker logs donchianbot --tail=20
```

---

## Fichier .env — variables requises

Stocké uniquement dans `/srv/data/donchianbot/.env` (jamais dans Git) :

```env
ALPACA_API_KEY=PK...
ALPACA_API_SECRET=...
DEMO_MODE=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DONCHIAN_LENGTH=100
LOOKBACK_CANDLES=500
RISK_PCT=0.005
POINT_VALUE=1.0
RR_RATIO=2.0
LOG_LEVEL=INFO
DATA_DIR=/app/data
```

Pour sauvegarder avant de changer de machine :
```bash
scp raspi-home:/srv/data/donchianbot/.env ~/Desktop/.env.donchianbot.backup
```
