# Runbook — Migration ZorionBot sur le Raspberry Pi

**Statut : non exécuté.** À lancer en septembre 2026, une fois Tailscale installé sur `raspi-home` (voir `docs/superpowers/specs/2026-08-24-rename-zorionbot-design.md`).

**Avant de commencer :**
- Confirmer que Tailscale est actif sur `raspi-home` et sur la machine qui exécute ce runbook.
- Vérifier `/status` sur Telegram — pas d'urgence à couper le bot en pleine gestion d'une position, même si le SL/TP restent gérés côté IG pendant l'arrêt.
- La PR qui renomme `docker-compose.yml` (service, `container_name`, volume, `env_file` vers `zorionbot`) doit être mergée sur `main` avant l'étape 5.

## 1. Sauvegarder les données actuelles

```bash
ssh raspi-home "tar -czf /tmp/donchianbot-backup-$(date +%Y%m%d).tar.gz -C /srv/data donchianbot"
scp raspi-home:/tmp/donchianbot-backup-*.tar.gz ~/Desktop/
```

## 2. Arrêter le bot

```bash
ssh raspi-home "cd ~/DonchianBot && docker compose down"
```

## 3. Renommer le dossier de données

```bash
ssh raspi-home "mv /srv/data/donchianbot /srv/data/zorionbot"
```

## 4. Renommer le clone du code et pointer sur le nouveau dépôt

```bash
ssh raspi-home "mv ~/DonchianBot ~/ZorionBot"
ssh raspi-home "cd ~/ZorionBot && git remote set-url origin https://github.com/Zorion83/ZorionBot.git"
ssh raspi-home "cd ~/ZorionBot && git pull"
```

## 5. Confirmer le contenu de docker-compose.yml

Après le `git pull` de l'étape 4, `~/ZorionBot/docker-compose.yml` doit contenir :

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
      - MR_TP_ATR=1.0
      - MR_TIME_STOP=48
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

Si ce n'est pas le cas (PR de migration pas encore mergée), appliquer ce contenu manuellement avant de continuer.

## 6. Reconstruire et redémarrer

```bash
ssh raspi-home "cd ~/ZorionBot && docker compose up -d --build"
```

## 7. Vérifier

```bash
ssh raspi-home "docker ps --filter name=zorionbot"
ssh raspi-home "docker logs zorionbot --tail=30"
```

Attendre la notification Telegram `🤖 ZorionBot démarré`. Vérifier `/status` sur Telegram : les positions ouvertes (s'il y en a) doivent apparaître avec leur SL/TP intacts.

Si le dashboard `homepage` (autre conteneur sur le même Pi, voir `docs/DOCKER_INFRASTRUCTURE.md`) référence le conteneur par son nom (`donchianbot`), mettre à jour sa configuration (`/srv/data/homepage/services.yaml` ou `docker.yaml`) pour pointer vers `zorionbot`.

## 8. Nettoyer (après quelques jours de fonctionnement stable confirmé)

```bash
ssh raspi-home "rm -f /tmp/donchianbot-backup-*.tar.gz"
```

Conserver la sauvegarde de l'étape 1 sur `~/Desktop/` plus longtemps, par précaution.

## 9. Mettre à jour les runbooks

Une fois la migration terminée, retirer le bandeau ajouté dans `docs/DOCKER_INFRASTRUCTURE.md` et `docs/TRANSFER.md` (Task 10 du plan de renommage) et remplacer partout `donchianbot`/`DonchianBot` par `zorionbot`/`ZorionBot` dans ces deux fichiers.
