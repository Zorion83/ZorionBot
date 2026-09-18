# Design — Deuxième instance ZorionBot (branche d'évolution de stratégie)

**Date :** 2026-09-18
**Statut :** Approuvé

---

## Contexte

Le bot en production (`donchianbot`, sur le Pi, compte démo IG #1, stratégie Mean Reversion XAUUSD v5 sur GOLD) tourne de façon stable (voir analyse des dernières 24h du 2026-09-18 : un seul incident réseau transitoire, auto-résolu, un trade clôturé en profit). Le propriétaire veut maintenant faire évoluer la stratégie sans risquer la stabilité ni le capital du bot actuel : besoin d'une deuxième instance complètement indépendante, avec son propre compte, son propre bot Telegram, pour itérer librement.

Deux options de compte ont été évaluées :
- Partager le compte/la clé API IG #1 entre les deux bots — **rejeté** : sessions API IG concurrentes qui s'invalident mutuellement, risque réel doublé à l'insu de chaque bot (chacun calcule sa taille de position sur le même solde sans connaître l'exposition de l'autre), conflit de suivi TP/SL sur le même epic GOLD, P&L illisible (capital partagé, impossible de comparer objectivement les deux stratégies).
- Un deuxième compte démo IG séparé — retenu par le propriétaire, obtenu après une difficulté initiale de création.

Contrainte de déploiement découverte en préparant ce design : contrairement à ce que documente `README.md` (`git clone` sur le Pi), le Pi **n'a pas de checkout Git** — `~/DonchianBot` y est un dossier simple, synchronisé par `rsync` depuis la machine de dev (voir `docs/DOCKER_INFRASTRUCTURE.md`). Le Git (branches, historique) vit uniquement sur les machines de dev (Mac / mini-PC) et sur GitHub. Le design ci-dessous en tient compte : l'isolation par branche/worktree se fait côté dev, le déploiement Pi reste un rsync vers un dossier séparé — exactement le même mécanisme que pour le bot 1, dupliqué.

Par ailleurs, la spec `2026-08-24-rename-zorionbot-design.md` mentionnait une « Phase 2 » — isolation de plusieurs stratégies **dans le même process/compte**, via sous-dossiers + registre de symboles. Ce projet n'est **pas** cette Phase 2 : il s'agit ici de deux process, deux comptes, deux containers entièrement séparés, pas d'une cohabitation multi-stratégies dans une même instance. Approche différente, choisie pour la garantie d'isolation qu'elle donne. La Phase 2 telle que décrite reste non traitée.

## Objectif

Déployer une deuxième instance de ZorionBot, code identique au bot 1 au démarrage (aucune évolution de stratégie dans ce lot), tournant en parallèle sur le Pi avec son propre compte IG démo, son propre bot Telegram, ses propres données persistées — sans aucune dépendance ni impact possible sur le bot 1 en production.

## Décisions validées avec le propriétaire

| Sujet | Décision |
|---|---|
| Compte de trading | 2ᵉ compte démo IG Markets (identifiant `Raspi_algo02`) — indépendant du compte du bot 1 |
| Bot Telegram | `@Raspi_algo02_bot`, chat privé `chat_id=793522682` |
| Isolation de code | Branche Git dédiée `evolve/meanrev-v2`, montée en **worktree** local (pas un second clone plein) depuis le repo existant |
| Actif tradé | GOLD, identique au bot 1 — comparaison directe des résultats dans les mêmes conditions de marché |
| Évolution de la stratégie | Hors périmètre de ce lot — le bot 2 démarre en copie exacte du code `main`, l'évolution est un travail séparé une fois le bot opérationnel |

## Architecture

### Isolation de code (machine de dev)
`git worktree add ../ZorionBot-v2 -b evolve/meanrev-v2 main` depuis le clone principal — dossier de travail séparé, mêmes objets Git, aucun second clone à maintenir en sync. Les futures évolutions de stratégie se développent et se committent sur cette branche.

### Déploiement Pi
Même mécanisme que le bot 1 (rsync + docker compose, pas de Git sur le Pi) :
- Nouveau dossier `~/DonchianBot-v2/` sur le Pi (contenu rsync depuis le worktree local, comme documenté pour le bot 1 dans `docs/DOCKER_INFRASTRUCTURE.md`)
- Nouveau `docker-compose.yml` dans ce dossier : `container_name: donchianbot-v2`, `build: .` (propre image, propre build), aucun port exposé
- Nouvelle donnée persistante : `/srv/data/donchianbot-v2/` (`.env`, `bot_state.json`, `candle_cache.json`, `trade_journal.json`, log rotatif) — aucun partage avec `/srv/data/donchianbot/`

Nommage `-v2` choisi pour rester cohérent avec l'infrastructure Pi réelle actuelle (`donchianbot`, pas encore migrée vers `zorionbot` — voir `docs/PI_MIGRATION_ZORIONBOT.md`, toujours en attente). Pas de renommage mêlé à ce lot.

### Config bot 2 (`.env`)
Identique au bot 1 au démarrage (mêmes paramètres `MR_*`, même `RISK_PCT`) à l'exception de :
- `IG_API_KEY` / `IG_IDENTIFIER=Raspi_algo02` / `IG_PASSWORD` — 2ᵉ compte démo
- `TELEGRAM_BOT_TOKEN` (bot `@Raspi_algo02_bot`) / `TELEGRAM_CHAT_ID=793522682`

Secrets fournis par le propriétaire directement dans le chat de cette session (canal non idéal, déjà fait) — écrits **uniquement** dans `/srv/data/donchianbot-v2/.env` sur le Pi via SSH, jamais commités, jamais réédités en clair dans ce repo ou dans une réponse. Recommandation transmise au propriétaire : faire tourner le mot de passe IG une fois le bot en place, par précaution.

### Isolation des pannes
Container, process, état et compte tous séparés → un bug ou crash dans la stratégie v2 ne peut pas affecter le bot 1. Seul risque partagé : une panne du Pi ou du réseau local lui-même (déjà vu absorbé par le retry existant dans les deux cas).

## Vérification

- `pytest` sur le worktree avant tout déploiement (suite existante, aucune modification de la logique testée dans ce lot)
- `docker compose config` sur le nouveau `docker-compose.yml` pour valider la syntaxe
- Post-déploiement : message Telegram de démarrage reçu sur `@Raspi_algo02_bot`, premier cycle visible dans `docker logs donchianbot-v2`, et confirmation que `docker logs donchianbot` (bot 1) ne montre aucune anomalie nouvelle pendant/après le déploiement

## Hors périmètre

- Évolution de la stratégie `strategy_meanrev.py` sur la branche v2 (travail futur, une fois le bot 2 confirmé stable)
- Bascule vers Alpaca paper trading (option évaluée puis abandonnée une fois le 2ᵉ compte IG obtenu)
- Phase 2 de `2026-08-24-rename-zorionbot-design.md` (isolation multi-stratégies dans un même process/compte)
- Migration Pi `donchianbot` → `zorionbot` (runbook existant, toujours en attente, non déclenchée par ce lot)
