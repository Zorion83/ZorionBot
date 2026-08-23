# Design — Renommage DonchianBot → ZorionBot (Phase 1)

**Date :** 2026-08-24
**Statut :** Approuvé

---

## Contexte

Le projet s'appelle `DonchianBot` alors que la stratégie qui a donné son nom au bot (Donchian V1.1) est aujourd'hui désactivée : la stratégie réellement live sur IG/Or est `Mean Reversion XAUUSD v5` (voir [main.py:597](../../../app/main.py)). Le propriétaire du projet veut renommer l'ensemble en `ZorionBot` (nom aligné avec son identité GitHub `Zorion83`), en vue d'accueillir plusieurs stratégies sur l'or à l'avenir (objet d'une Phase 2 séparée : isolation des stratégies en sous-dossiers + registre de symboles de suivi de performance).

Le bot tourne en production sur un Raspberry Pi (`raspi-home`, IP LAN privée `192.168.1.197`), injoignable depuis cet environnement d'exécution (pas de VPN/Tailscale vers ce host). Le déploiement sur le Pi est **manuel** (`git pull && docker compose up -d --build`, jamais automatique) — donc un renommage du code et du dépôt GitHub n'affecte pas le bot tant que personne ne redéploie manuellement. Le propriétaire ne pourra pas installer Tailscale sur le Pi avant mi-septembre 2026 et ne veut prendre aucun risque sur le fonctionnement du bot actuel avant cette date.

## Objectif

Renommer intégralement le projet en `ZorionBot` — code, dépôt GitHub, documentation, dossier local — **sans aucun impact sur le bot en production**, y compris si un déploiement manuel non lié à ce chantier a lieu sur le Pi avant la migration de septembre.

## Contrainte non négociable

Un `git pull && docker compose up -d --build` lancé sur le Pi à n'importe quel moment entre ce merge et la migration de septembre doit se comporter **à l'identique** d'aujourd'hui : même conteneur (`donchianbot`), même volume (`/srv/data/donchianbot`), même fichier `.env`. Aucune casse silencieuse (clés API introuvables, perte du cache de bougies, du `bot_state.json` ou du `trade_journal.json`).

---

## Périmètre — ce qui change dans cette Phase 1

### Code applicatif (`app/`)
- [`config.py`](../../../app/config.py) — `LOG_FILE` : `donchianbot.log` → `zorionbot.log`. Sans risque : nouveau fichier créé dans un dossier déjà monté ; l'ancien log reste lisible, pas de perte.
- [`main.py`](../../../app/main.py) — nom du logger (`"DonchianBot"` → `"ZorionBot"`), bannière de démarrage/arrêt (ASCII box à réaligner selon la nouvelle longueur), messages `/status`, commentaire d'ordre broker (`comment=f"DonchianBot_{asset_name}"` → `f"ZorionBot_{asset_name}"` — visible dans l'historique IG, purement cosmétique, les ordres passés avant/après auront juste un tag différent).
- [`telegram_notifier.py`](../../../app/telegram_notifier.py) — 3 messages Telegram visibles par l'utilisateur (connexion, démarrage, résumé quotidien).
- [`assets_config.py`](../../../app/assets_config.py) — en-tête de commentaire.

### Tests
- [`tests/conftest.py`](../../../tests/conftest.py) — préfixe `tempfile.mkdtemp` (`donchianbot_test_` → `zorionbot_test_`). Aucun test n'assert le nom actuel — vérification faite, à confirmer par un run `pytest` après renommage.

### Dépôt GitHub
- `gh repo rename ZorionBot` sur `Zorion83/DonchianBot` (dépôt privé, scope `repo` disponible sur le token courant).
- Mise à jour du remote `origin` en local — **dans ce worktree ET dans le clone principal du Mac** (`git -C <chemin> remote set-url origin ...`), indépendamment du renommage du dossier (peut se faire tout de suite après le rename GitHub).

### Documentation
- **README.md** — renommage complet (titre, URL de clone, chemins d'installation `/srv/data/...`, arborescence). C'est le guide d'installation générique : toute nouvelle installation (nouveau serveur, reproduction) doit utiliser directement les nouveaux noms.
- **Specs/plans historiques** :
  - `docs/superpowers/plans/2026-03-20-donchianbot.md` et `docs/superpowers/specs/2026-03-20-donchianbot-design.md` — contenu renommé **et fichiers renommés** (`2026-03-20-donchianbot*.md` → `2026-03-20-zorionbot*.md`, le nom du projet étant dans le nom de fichier).
  - `docs/superpowers/plans/2026-04-16-position-tracking.md` et `docs/superpowers/specs/2026-04-16-position-tracking-design.md` — contenu renommé uniquement (le nom du projet n'apparaît pas dans le nom de fichier, pas de `git mv` nécessaire).

### Ce qui NE change PAS dans cette Phase 1 (volontairement)
- **`docker-compose.yml`** — `container_name`, nom de service, chemin du volume (`/srv/data/donchianbot`), `env_file` : **inchangés**. C'est la garantie que le bot actuel n'est pas affecté par un déploiement manuel avant septembre.
- **`docs/DOCKER_INFRASTRUCTURE.md` et `docs/TRANSFER.md`** — ce sont des runbooks qui décrivent l'infrastructure Pi **telle qu'elle existe réellement aujourd'hui** (chemins `/srv/data/donchianbot`, conteneur `donchianbot`, dossier `~/DonchianBot` sur le Pi). Les réécrire maintenant les rendrait faux tant que la migration n'a pas eu lieu. Traitement : ajout d'un bandeau en tête de chaque document indiquant que la migration vers `ZorionBot` est prévue pour septembre 2026 (renvoi vers le runbook de migration), mise à jour de la seule URL de clone GitHub. Le reste (chemins, noms de conteneur) reste `donchianbot` jusqu'à la migration réelle.
- **`Dockerfile`** — aucune référence au nom du projet, rien à changer.

---

## Migration Pi (hors périmètre d'exécution immédiat)

Livrable de cette Phase 1 : `docs/PI_MIGRATION_ZORIONBOT.md`, un runbook prêt à l'emploi couvrant, dans l'ordre :
1. Arrêt du conteneur (`docker compose down`).
2. `mv /srv/data/donchianbot /srv/data/zorionbot`.
3. `mv ~/DonchianBot ~/ZorionBot` sur le Pi, mise à jour du remote git.
4. Mise à jour de `docker-compose.yml` (service/`container_name`/volume/`env_file`) — ce diff sera préparé dans une PR séparée à merger seulement au moment de la migration.
5. `docker compose up -d --build`, vérification des logs et de la notification Telegram de démarrage.

Ce runbook n'est **pas exécuté** dans le cadre de cette Phase 1. Il sera utilisé en septembre 2026, quand Tailscale sera disponible sur le Pi (ce qui permettra aussi une exécution assistée à distance plutôt que manuelle).

## Renommage du dossier local (Mac)

Le dossier racine du clone principal (`~/01_PROJETS/00_DEV/Algo_B&G/DonchianBot`) sera renommé en `ZorionBot` **après le merge sur `main`**, en dehors de ce worktree (qui vit physiquement dans ce même dossier et ne peut pas renommer son propre parent pendant qu'il est actif). Étapes : merge → nettoyage du worktree → `mv` du dossier principal → `git worktree repair` si d'autres worktrees existent encore.

---

## Vérification

- `pytest` (suite complète) après renommage du code et des tests.
- `docker compose config` sur `docker-compose.yml` pour confirmer qu'il reste syntaxiquement valide (il n'est pas modifié, donc régression nulle attendue — vérification de non-régression).
- Grep final de contrôle : `grep -rniE "donchianbot"` sur le repo doit ne plus remonter que les occurrences volontairement conservées (`docker-compose.yml`, `docs/DOCKER_INFRASTRUCTURE.md`, `docs/TRANSFER.md`).

## Hors périmètre (rappel)

- Phase 2 : isolation des stratégies dans des sous-dossiers dédiés + registre de symboles de suivi des performances (Mean Reversion v5 = symbole 1️⃣, stratégies inactives = code 99). Fera l'objet d'un design séparé une fois cette Phase 1 mergée.
- Correction du contenu obsolète de `TRANSFER.md`/`DOCKER_INFRASTRUCTURE.md` (mentions d'Alpaca/SPY/QQQ/BTC comme stratégie "actuelle" alors que c'est Mean Reversion/Or/IG aujourd'hui) — signalé au propriétaire, non traité ici.
