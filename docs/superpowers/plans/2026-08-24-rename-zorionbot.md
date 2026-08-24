# Renommage ZorionBot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Renommer le projet `DonchianBot` en `ZorionBot` (code, tests, dépôt GitHub, documentation, dossier local sur Mac et minipc, vault Obsidian) sans jamais casser le bot en production sur le Pi.

**Architecture:** Pur renommage mécanique, aucune nouvelle logique — pas de cycle TDD rouge/vert classique. La discipline appliquée à la place : chaque fichier de code touché est suivi d'un run de la suite de tests complète (régression), et chaque groupe de fichiers renommés est suivi d'une vérification `grep` exacte. Deux règles de fond, déjà actées dans la spec, gouvernent tous les choix ligne à ligne :
1. Les identifiants qui désignent la **stratégie Donchian elle-même** (ex : `DONCHIAN_LENGTH`, "stratégie Donchian V1.1") ne sont **jamais** renommés — seul le nom du **projet/bot** change.
2. Les fichiers qui décrivent l'**infrastructure Pi réelle actuelle** (`docker-compose.yml`, `docs/DOCKER_INFRASTRUCTURE.md`, `docs/TRANSFER.md`, et les notes d'infra du vault Obsidian) gardent les chemins `donchianbot` tant que la migration Pi (Tâche 12, hors exécution immédiate) n'a pas eu lieu — un `git pull && docker compose up -d --build` sur le Pi avant septembre 2026 doit se comporter à l'identique d'aujourd'hui.

**Tech Stack:** Python 3.11 / pytest, Docker Compose, GitHub CLI (`gh`), Git worktrees, SSH (minipc via Tailscale), PowerShell (minipc), Markdown.

**Spec de référence :** `docs/superpowers/specs/2026-08-24-rename-zorionbot-design.md`

---

## Groupe A — Code applicatif et tests (dans ce worktree)

### Task 1: `app/config.py` — nom du fichier de log

**Files:**
- Modify: `app/config.py:46`

- [ ] **Step 1: Éditer la ligne**

Avant :
```python
LOG_FILE  = os.path.join(DATA_DIR, "donchianbot.log")
```

Après :
```python
LOG_FILE  = os.path.join(DATA_DIR, "zorionbot.log")
```

Ne pas toucher aux lignes 22-23 (`héritage Donchian`, `DONCHIAN_LENGTH`) — elles désignent la stratégie, pas le projet.

- [ ] **Step 2: Vérifier qu'il ne reste que les références stratégie**

Run: `grep -ni "donchian" app/config.py`
Expected:
```
app/config.py:22:# ── Strategy (héritage Donchian) ──────────────────────────────────
app/config.py:23:DONCHIAN_LENGTH   = int(os.environ.get("DONCHIAN_LENGTH", "100"))
```

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "rename: zorionbot.log dans config.py"
```

---

### Task 2: `app/assets_config.py` — en-tête de commentaire

**Files:**
- Modify: `app/assets_config.py:2`

- [ ] **Step 1: Éditer la ligne**

Avant :
```python
# assets_config.py — Asset configuration for DonchianBot (Alpaca Markets)
```

Après :
```python
# assets_config.py — Asset configuration for ZorionBot (Alpaca Markets)
```

- [ ] **Step 2: Commit**

```bash
git add app/assets_config.py
git commit -m "rename: en-tête assets_config.py"
```

---

### Task 3: `tests/conftest.py` — préfixe du dossier temporaire

**Files:**
- Modify: `tests/conftest.py:6`

- [ ] **Step 1: Éditer la ligne**

Avant :
```python
_tmp_data = tempfile.mkdtemp(prefix="donchianbot_test_")
```

Après :
```python
_tmp_data = tempfile.mkdtemp(prefix="zorionbot_test_")
```

- [ ] **Step 2: Commit**

```bash
git add tests/conftest.py
git commit -m "rename: préfixe tempdir des tests"
```

---

### Task 4: `app/telegram_notifier.py` — 3 messages Telegram visibles

**Files:**
- Modify: `app/telegram_notifier.py:160,168,214`

- [ ] **Step 1: Éditer les 3 occurrences**

Ligne 160, avant :
```python
        await self._send("✅ DonchianBot connecté et opérationnel.")
```
après :
```python
        await self._send("✅ ZorionBot connecté et opérationnel.")
```

Ligne 168, avant :
```python
            f"🤖 <b>DonchianBot démarré</b>\n"
```
après :
```python
            f"🤖 <b>ZorionBot démarré</b>\n"
```

Ligne 214, avant :
```python
            f"📊 <b>DonchianBot — Résumé du {today}</b>",
```
après :
```python
            f"📊 <b>ZorionBot — Résumé du {today}</b>",
```

- [ ] **Step 2: Vérifier qu'il n'en reste aucune**

Run: `grep -ni "donchian" app/telegram_notifier.py`
Expected: (aucune sortie)

- [ ] **Step 3: Commit**

```bash
git add app/telegram_notifier.py
git commit -m "rename: messages Telegram ZorionBot"
```

---

### Task 5: `app/main.py` — logger, bannières, commande broker

**Files:**
- Modify: `app/main.py:55,299,317,709,715,765,871`

- [ ] **Step 1: Renommer le logger (ligne 55)**

Avant :
```python
logger = logging.getLogger("DonchianBot")
```
après :
```python
logger = logging.getLogger("ZorionBot")
```

- [ ] **Step 2: En-tête de `/help` (ligne 299)**

Avant :
```python
            "🤖 <b>DonchianBot — Commandes</b>\n\n"
```
après :
```python
            "🤖 <b>ZorionBot — Commandes</b>\n\n"
```

- [ ] **Step 3: En-tête de `/status` (ligne 317)**

Avant :
```python
                f"🤖 <b>{mode_tag}DonchianBot</b>",
```
après :
```python
                f"🤖 <b>{mode_tag}ZorionBot</b>",
```

- [ ] **Step 4: Commentaire d'ordre broker (lignes 709 et 715)**

Les deux occurrences sont identiques, dans `open_long` et `open_short` :

Avant :
```python
                        comment=f"DonchianBot_{asset_name}",
```
après (aux deux endroits) :
```python
                        comment=f"ZorionBot_{asset_name}",
```

- [ ] **Step 5: Bannière de démarrage (ligne 765) — largeur de la boîte ASCII à préserver**

Avant :
```python
    logger.info("║   DonchianBot started        ║")
```
après (32 caractères au total, identique à `╔══...══╗` et `╚══...══╝` qui restent inchangés) :
```python
    logger.info("║   ZorionBot started          ║")
```

- [ ] **Step 6: Message d'arrêt (ligne 871)**

Avant :
```python
        logger.info("DonchianBot stopped.")
```
après :
```python
        logger.info("ZorionBot stopped.")
```

- [ ] **Step 7: Vérifier qu'il ne reste que les 2 références stratégie légitimes**

Run: `grep -ni "donchian" app/main.py`
Expected:
```
app/main.py:4:Strategy : Mean Reversion XAUUSD v5 (BROKER=ig) ou Donchian V1.1 (BROKER=alpaca)
app/main.py:622:    donchian_length     = DONCHIAN_LENGTH,
```

- [ ] **Step 8: Commit**

```bash
git add app/main.py
git commit -m "rename: logger, bannières et messages ZorionBot dans main.py"
```

---

### Task 6: Suite de tests complète — vérification de non-régression

**Files:**
- (aucun fichier modifié, vérification uniquement)

- [ ] **Step 1: Installer les dépendances de dev si besoin**

Run: `pip install -r requirements-dev.txt -r app/requirements.txt`

- [ ] **Step 2: Lancer la suite complète**

Run: `pytest tests/ -v`
Expected: tous les tests passent (35 tests avant renommage — le compte ne doit pas baisser), aucune erreur d'import.

- [ ] **Step 3: Si un test échoue à cause d'une chaîne codée en dur ailleurs**

Chercher la chaîne fautive :
```bash
grep -rn "DonchianBot\|donchianbot" tests/ app/
```
Si une occurrence légitime de "DonchianBot" est trouvée dans un test (aucune connue à ce jour dans la spec), la mettre à jour en cohérence avec les Tasks 1-5, puis relancer `pytest tests/ -v`.

---

## Groupe B — Documentation dans ce dépôt

### Task 7: `README.md` — renommage complet

**Files:**
- Modify: `README.md` (13 occurrences : titre, URL de clone x2, arborescence, chemins `/srv/data` x2, dossier cloné x2)

- [ ] **Step 1: Remplacement global**

Run:
```bash
sed -i '' 's/DonchianBot/ZorionBot/g; s/donchianbot/zorionbot/g' README.md
```

- [ ] **Step 2: Vérifier qu'il ne reste aucune occurrence**

Run: `grep -ni "donchianbot" README.md`
Expected: (aucune sortie)

- [ ] **Step 3: Relire le diff pour confirmer qu'aucune ligne de stratégie n'a été touchée par erreur**

Run: `git diff README.md`
Expected: les lignes 15 (`canal de Donchian`) et 106 (`Période du canal de Donchian`) sont **absentes du diff** — elles ne contiennent que "Donchian" seul (sans "Bot"), non concerné par le sed.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "rename: README.md vers ZorionBot"
```

---

### Task 8: Specs et plans historiques du 2026-03-20 — contenu + noms de fichiers

**Files:**
- Rename: `docs/superpowers/plans/2026-03-20-donchianbot.md` → `docs/superpowers/plans/2026-03-20-zorionbot.md`
- Rename: `docs/superpowers/specs/2026-03-20-donchianbot-design.md` → `docs/superpowers/specs/2026-03-20-zorionbot-design.md`

- [ ] **Step 1: Renommer les fichiers avec `git mv` (préserve l'historique)**

```bash
git mv docs/superpowers/plans/2026-03-20-donchianbot.md docs/superpowers/plans/2026-03-20-zorionbot.md
git mv docs/superpowers/specs/2026-03-20-donchianbot-design.md docs/superpowers/specs/2026-03-20-zorionbot-design.md
```

- [ ] **Step 2: Remplacement du contenu**

```bash
sed -i '' 's/DonchianBot/ZorionBot/g; s/donchianbot/zorionbot/g' docs/superpowers/plans/2026-03-20-zorionbot.md
sed -i '' 's/DonchianBot/ZorionBot/g; s/donchianbot/zorionbot/g' docs/superpowers/specs/2026-03-20-zorionbot-design.md
```

- [ ] **Step 3: Vérifier**

Run: `grep -rni "donchianbot" docs/superpowers/plans/2026-03-20-zorionbot.md docs/superpowers/specs/2026-03-20-zorionbot-design.md`
Expected: (aucune sortie)

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-03-20-zorionbot.md docs/superpowers/specs/2026-03-20-zorionbot-design.md
git commit -m "rename: specs/plans historiques du 2026-03-20 vers ZorionBot"
```

---

### Task 9: Specs et plans du 2026-04-16 — contenu seulement

**Files:**
- Modify: `docs/superpowers/plans/2026-04-16-position-tracking.md`
- Modify: `docs/superpowers/specs/2026-04-16-position-tracking-design.md`

Ces fichiers ne portent pas "donchianbot" dans leur nom : pas de `git mv`, contenu uniquement.

- [ ] **Step 1: Remplacement du contenu**

```bash
sed -i '' 's/DonchianBot/ZorionBot/g; s/donchianbot/zorionbot/g' docs/superpowers/plans/2026-04-16-position-tracking.md
sed -i '' 's/DonchianBot/ZorionBot/g; s/donchianbot/zorionbot/g' docs/superpowers/specs/2026-04-16-position-tracking-design.md
```

- [ ] **Step 2: Vérifier**

Run: `grep -rni "donchianbot" docs/superpowers/plans/2026-04-16-position-tracking.md docs/superpowers/specs/2026-04-16-position-tracking-design.md`
Expected: (aucune sortie)

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-04-16-position-tracking.md docs/superpowers/specs/2026-04-16-position-tracking-design.md
git commit -m "rename: specs/plans du 2026-04-16 vers ZorionBot"
```

---

### Task 10: `docs/DOCKER_INFRASTRUCTURE.md` et `docs/TRANSFER.md` — bandeau + URL uniquement

**Files:**
- Modify: `docs/DOCKER_INFRASTRUCTURE.md:1-6,233`
- Modify: `docs/TRANSFER.md:1-6`

Ces deux documents décrivent l'infrastructure Pi **réelle actuelle** — ils gardent `donchianbot` partout sauf le bandeau d'avertissement et l'URL GitHub.

- [ ] **Step 1: Ajouter le bandeau dans `docs/DOCKER_INFRASTRUCTURE.md`**

Avant (ligne 1-6) :
```markdown
# Infrastructure Docker — Raspberry Pi 5

> **Note importante** : Docker tourne sur le **Raspberry Pi**, pas sur le Mac.
> Le Mac est uniquement la machine de développement (éditeur de code + déploiement via SSH/rsync).
> Ce document décrit l'infrastructure à reproduire si tu changes de Raspi.
```

Après :
```markdown
# Infrastructure Docker — Raspberry Pi 5

> ⚠️ **Renommage du projet en cours (2026-08)** : `DonchianBot` devient `ZorionBot`. Ce document décrit encore l'infrastructure réelle du Pi sous l'ancien nom (`donchianbot`, `/srv/data/donchianbot`) — ces chemins ne changeront qu'à la migration planifiée pour septembre 2026. Voir [`docs/PI_MIGRATION_ZORIONBOT.md`](./PI_MIGRATION_ZORIONBOT.md).

> **Note importante** : Docker tourne sur le **Raspberry Pi**, pas sur le Mac.
> Le Mac est uniquement la machine de développement (éditeur de code + déploiement via SSH/rsync).
> Ce document décrit l'infrastructure à reproduire si tu changes de Raspi.
```

- [ ] **Step 2: Mettre à jour uniquement l'URL GitHub dans `docs/DOCKER_INFRASTRUCTURE.md`**

Chercher la ligne (section 4, autour de la ligne 233) :

Avant :
```bash
git clone https://github.com/Zorion83/DonchianBot.git ~/DonchianBot
```

Après (l'URL change, le dossier de destination reste `~/DonchianBot` car c'est le nom réel du dossier sur le Pi tant que la migration n'a pas eu lieu) :
```bash
git clone https://github.com/Zorion83/ZorionBot.git ~/DonchianBot
```

- [ ] **Step 3: Ajouter le bandeau dans `docs/TRANSFER.md`**

Avant (ligne 1-6) :
```markdown
# DonchianBot — Document de transfert vers nouvelle machine

> **Usage** : Ce document est destiné à Claude Code pour reconfigurer l'environnement de
> développement sur une nouvelle machine Mac, à partir d'un clone Git du projet.
> Il couvre : SSH, déploiement Raspi, règles critiques, état du code.
```

Après :
```markdown
# DonchianBot — Document de transfert vers nouvelle machine

> ⚠️ **Renommage du projet en cours (2026-08)** : `DonchianBot` devient `ZorionBot`. Ce document décrit encore l'infrastructure réelle du Pi sous l'ancien nom (`donchianbot`, `/srv/data/donchianbot`) — ces chemins ne changeront qu'à la migration planifiée pour septembre 2026. Voir [`docs/PI_MIGRATION_ZORIONBOT.md`](./PI_MIGRATION_ZORIONBOT.md).

> **Usage** : Ce document est destiné à Claude Code pour reconfigurer l'environnement de
> développement sur une nouvelle machine Mac, à partir d'un clone Git du projet.
> Il couvre : SSH, déploiement Raspi, règles critiques, état du code.
```

- [ ] **Step 4: Vérifier qu'aucun autre changement n'a été introduit**

Run: `git diff docs/DOCKER_INFRASTRUCTURE.md docs/TRANSFER.md`
Expected: seuls les 2 bandeaux ajoutés et l'URL de la Step 2 apparaissent dans le diff — aucune autre ligne touchée.

- [ ] **Step 5: Commit**

```bash
git add docs/DOCKER_INFRASTRUCTURE.md docs/TRANSFER.md
git commit -m "docs: bandeau de transition ZorionBot sur les runbooks d'infra Pi"
```

---

### Task 11: Créer le runbook de migration Pi

**Files:**
- Create: `docs/PI_MIGRATION_ZORIONBOT.md`

- [ ] **Step 1: Créer le fichier**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/PI_MIGRATION_ZORIONBOT.md
git commit -m "docs: runbook de migration Pi vers ZorionBot (à exécuter en septembre 2026)"
```

---

## Groupe C — Dépôt GitHub et vérification finale

### Task 12: Renommer le dépôt GitHub et mettre à jour le remote de ce worktree

**Files:**
- (aucun fichier — opération GitHub + config git locale)

- [ ] **Step 1: Confirmer l'état actuel du dépôt**

Run: `gh repo view Zorion83/DonchianBot --json name,visibility`
Expected: `{"name":"DonchianBot","visibility":"PRIVATE"}`

- [ ] **Step 2: Renommer le dépôt**

Run: `gh repo rename ZorionBot --repo Zorion83/DonchianBot --yes`
Expected: confirmation de renommage, nouvelle URL `https://github.com/Zorion83/ZorionBot`

- [ ] **Step 3: Mettre à jour le remote `origin` de ce worktree**

```bash
git remote set-url origin https://github.com/Zorion83/ZorionBot.git
git remote -v
```
Expected : `origin` pointe vers `https://github.com/Zorion83/ZorionBot.git` (fetch et push).

- [ ] **Step 4: Mettre à jour le remote du clone principal Mac**

```bash
git -C "/Users/remyclaudel/01_PROJETS/00_DEV/Algo_B&G/DonchianBot" remote set-url origin https://github.com/Zorion83/ZorionBot.git
git -C "/Users/remyclaudel/01_PROJETS/00_DEV/Algo_B&G/DonchianBot" remote -v
```
Expected : même résultat que Step 3, sur le clone principal (indépendant du renommage physique du dossier, traité en Task 15).

---

### Task 13: Vérification finale et push de la branche

**Files:**
- (aucun fichier — vérification uniquement)

- [ ] **Step 1: Grep final sur tout le dépôt**

Run: `grep -rniE "donchianbot" --include="*.py" --include="*.md" --include="*.yml" --include="*.yaml" . 2>/dev/null | grep -v '.git/'`
Expected : seules ces occurrences restantes (toutes volontaires, voir Task 10) :
```
./docker-compose.yml (3 lignes : service, container_name, volumes/env_file)
./docs/DOCKER_INFRASTRUCTURE.md (bandeau exclu, chemins/commandes réels du Pi)
./docs/TRANSFER.md (bandeau exclu, chemins/commandes réels du Pi)
```

- [ ] **Step 2: Valider que `docker-compose.yml` est syntaxiquement inchangé et valide**

Run: `docker compose config --quiet && echo "compose OK"`
Expected: `compose OK` (aucune erreur — le fichier n'a pas été modifié dans ce plan)

- [ ] **Step 3: Suite de tests complète une dernière fois**

Run: `pytest tests/ -v`
Expected: tous les tests passent.

- [ ] **Step 4: Push de la branche**

```bash
git push -u origin claude/rename-donchianbot-zorionbot-34829c
```

- [ ] **Step 5: Ouvrir la PR**

```bash
gh pr create --title "Renommage DonchianBot -> ZorionBot (Phase 1 : code, docs, dépôt)" --body "$(cat <<'EOF'
## Résumé
- Renomme le projet DonchianBot -> ZorionBot dans le code, les tests, la documentation et le dépôt GitHub.
- docker-compose.yml et les runbooks d'infra Pi (DOCKER_INFRASTRUCTURE.md, TRANSFER.md) gardent volontairement les chemins `donchianbot` réels jusqu'à la migration Pi de septembre 2026 (voir docs/PI_MIGRATION_ZORIONBOT.md) — aucun impact sur le bot en production.
- Spec : docs/superpowers/specs/2026-08-24-rename-zorionbot-design.md

## Test plan
- [x] `pytest tests/ -v` — suite complète verte
- [x] `docker compose config --quiet` — compose toujours valide
- [x] grep final — seules les occurrences volontaires (compose + runbooks d'infra) subsistent
EOF
)"
```

---

## Groupe D — Après le merge sur `main` (hors de ce worktree)

Ces tâches ne peuvent pas s'exécuter depuis l'intérieur de ce worktree (qui vit physiquement dans le dossier qu'on renomme en Task 14). À faire une fois la PR de la Task 13 mergée, dans une session normale (pas un worktree) sur le Mac.

### Task 14: Renommer le dossier local principal (Mac)

**Files:**
- (opération filesystem)

- [ ] **Step 1: Vérifier qu'il n'y a aucun travail non commité**

```bash
git -C "/Users/remyclaudel/01_PROJETS/00_DEV/Algo_B&G/DonchianBot" status
```
Expected: `nothing to commit, working tree clean` (sur `main`, à jour avec `origin/main`).

- [ ] **Step 2: Nettoyer le worktree de cette branche s'il existe encore**

```bash
git -C "/Users/remyclaudel/01_PROJETS/00_DEV/Algo_B&G/DonchianBot" worktree remove .claude/worktrees/rename-donchianbot-zorionbot-34829c
```

- [ ] **Step 3: Renommer le dossier**

```bash
mv "/Users/remyclaudel/01_PROJETS/00_DEV/Algo_B&G/DonchianBot" "/Users/remyclaudel/01_PROJETS/00_DEV/Algo_B&G/ZorionBot"
```

- [ ] **Step 4: Réparer les références de worktrees restants**

```bash
git -C "/Users/remyclaudel/01_PROJETS/00_DEV/Algo_B&G/ZorionBot" worktree repair
git -C "/Users/remyclaudel/01_PROJETS/00_DEV/Algo_B&G/ZorionBot" worktree list
```
Expected: la liste ne montre plus que des chemins sous `ZorionBot/`.

---

### Task 15: minipc — clone git

**Files:**
- (opération filesystem + git, sur `minipc` via SSH)

- [ ] **Step 1: Vérifier qu'il n'y a aucun travail non commité sur le clone minipc**

```bash
ssh -o RemoteCommand=none minipc "powershell -NoProfile -Command \"cd 'C:\Users\Zorion-AI\Documents\Claude\Projects\Dev - Raspi - GitHub\DonchianBot'; git status\""
```
Expected: `nothing to commit, working tree clean`. Si des changements existent, les committer/stasher avant de continuer (ne jamais écraser du travail en cours — voir la garde-fou de sécurité générale).

- [ ] **Step 2: Mettre à jour le remote et puller `main`**

```bash
ssh -o RemoteCommand=none minipc "powershell -NoProfile -Command \"cd 'C:\Users\Zorion-AI\Documents\Claude\Projects\Dev - Raspi - GitHub\DonchianBot'; git remote set-url origin https://github.com/Zorion83/ZorionBot.git; git checkout main; git pull\""
```

- [ ] **Step 3: Renommer le dossier**

```bash
ssh -o RemoteCommand=none minipc "powershell -NoProfile -Command \"Rename-Item -Path 'C:\Users\Zorion-AI\Documents\Claude\Projects\Dev - Raspi - GitHub\DonchianBot' -NewName 'ZorionBot'\""
```

- [ ] **Step 4: Vérifier**

```bash
ssh -o RemoteCommand=none minipc "powershell -NoProfile -Command \"cd 'C:\Users\Zorion-AI\Documents\Claude\Projects\Dev - Raspi - GitHub\ZorionBot'; git remote -v; git log -1 --oneline\""
```
Expected: `origin` pointe vers `ZorionBot.git`, dernier commit = celui de la PR mergée (Task 13).

---

### Task 16: minipc — vault Obsidian (traitement manuel assisté, pas de sed aveugle)

**Files:**
- Rename (dossier) : `Documents\Zorion-AI's brain\Projects\DonchianBot` → `Projects\ZorionBot`
- Modify (contenu, avec tri manuel) : les 10 fichiers `.md` de ce dossier

**Ce groupe ne suit pas la mécanique sed des Tasks 7-9.** Ces notes contiennent des commandes et chemins qui, comme `docs/DOCKER_INFRASTRUCTURE.md`, décrivent l'infra Pi réelle actuelle (`Configurations.md`, `Déploiement.md`, `Infrastructure.md`, `Commandes utiles.md`, `Accès SSH.md`, `Variables env.md` ont chacune 1 à 13 occurrences de "donchianbot"). Un remplacement global casserait leur exactitude vis-à-vis du Pi réel, exactement comme discuté en Task 10. Procédure :

- [ ] **Step 1: Renommer le dossier**

```bash
ssh -o RemoteCommand=none minipc "powershell -NoProfile -Command \"Rename-Item -Path 'C:\Users\Zorion-AI\Documents\Zorion-AI''s brain\Projects\DonchianBot' -NewName 'ZorionBot'\""
```

- [ ] **Step 2: Pour chaque fichier `.md` du dossier, lire le contenu et appliquer la même règle que Task 10**

Fichiers à traiter : `00 - Index.md`, `Commandes utiles.md`, `Configurations.md`, `Décisions.md`, `Déploiement.md`, `Infrastructure.md`, `Mobile & monitoring.md`, `Trades.md`, `Variables env.md`, `Accès SSH.md`.

Pour chaque fichier :
1. Récupérer le contenu : `ssh -o RemoteCommand=none minipc "powershell -NoProfile -Command \"Get-Content -Raw -Encoding UTF8 'C:\Users\Zorion-AI\Documents\Zorion-AI''s brain\Projects\ZorionBot\<fichier>'\""`.
2. Classer chaque occurrence de "donchianbot"/"DonchianBot" :
   - **Nom de projet / titre / mention générale** (ex : "# Projet DonchianBot", "Notes DonchianBot") → renommer en "ZorionBot".
   - **Chemin ou commande littérale décrivant le Pi réel aujourd'hui** (`/srv/data/donchianbot`, `~/DonchianBot`, `container_name: donchianbot`, `docker logs donchianbot`, IP/identifiants inchangés) → **laisser tel quel**, exactement comme dans `docs/DOCKER_INFRASTRUCTURE.md`.
   - Ne **jamais** modifier une valeur (mot de passe, token, IP, clé) — uniquement le texte "DonchianBot"/"donchianbot" quand il s'agit d'une mention de nom de projet.
3. Écrire le contenu corrigé en préservant l'encodage UTF-8 sans BOM (celui d'Obsidian) :
   `ssh -o RemoteCommand=none minipc "powershell -NoProfile -Command \"[System.IO.File]::WriteAllText('C:\Users\Zorion-AI\Documents\Zorion-AI''s brain\Projects\ZorionBot\<fichier>', \$content, (New-Object System.Text.UTF8Encoding \$false))\""` (`$content` = variable contenant le texte corrigé, construite dans la même session PowerShell après relecture — ne pas faire transiter le contenu complet des notes sensibles par un fichier intermédiaire commité dans ce dépôt).
4. Ajouter, dans le même fichier, une ligne de bandeau au sommet, cohérente avec Task 10 :
   `> ⚠️ Renommage du projet en cours (2026-08) : DonchianBot devient ZorionBot. Ce fichier garde encore des chemins/commandes réels du Pi sous l'ancien nom jusqu'à la migration de septembre 2026.` — uniquement dans les fichiers où au moins une occurrence a été **laissée telle quelle** à l'étape 2 (`Configurations.md`, `Déploiement.md`, `Infrastructure.md`, `Commandes utiles.md`, `Accès SSH.md`, `Variables env.md`).

- [ ] **Step 3: Vérifier qu'aucune valeur sensible n'a été altérée**

Pour `Accès SSH.md` et `Variables env.md` spécifiquement : comparer un extrait avant/après (uniquement les lignes contenant "donchian", via `Select-String`) pour confirmer que seul le texte "DonchianBot"/"donchianbot" a changé, jamais une IP, un identifiant ou un mot de passe.

- [ ] **Step 4: Compte de contrôle final**

```bash
ssh -o RemoteCommand=none minipc "powershell -NoProfile -Command \"Get-ChildItem 'C:\Users\Zorion-AI\Documents\Zorion-AI''s brain\Projects\ZorionBot' -Filter '*.md' | ForEach-Object { \$c = (Select-String -Path \$_.FullName -Pattern 'donchianbot' -AllMatches -CaseSensitive:\$false | Measure-Object).Count; Write-Host (\$_.Name + ': ' + \$c) }\""
```
Expected : chaque compte restant correspond exactement aux occurrences volontairement laissées (chemins/commandes Pi réels) identifiées à l'étape 2 pour ce fichier — pas une de plus, pas une de moins que ce qui a été délibérément conservé.

---

## Self-Review (fait par l'auteur du plan)

- **Couverture de la spec** : périmètre code (Tasks 1-6), docs du dépôt (Tasks 7-11), GitHub + vérif (Tasks 12-13), post-merge Mac (Task 14), addendum minipc clone (Task 15) et vault (Task 16) — tous les points de `docs/superpowers/specs/2026-08-24-rename-zorionbot-design.md` sont couverts, y compris son addendum.
- **Cohérence des types/noms** : `zorionbot.log`, logger `"ZorionBot"`, préfixe tempdir `zorionbot_test_`, commentaire d'ordre `ZorionBot_{asset_name}` — cohérents entre eux et avec la spec.
- **Pas de placeholder** : chaque step a une commande ou un diff exact ; la Task 16 ne fixe pas de contenu littéral de notes personnelles (pour ne pas faire transiter de données sensibles dans ce dépôt) mais donne une règle de décision précise et des commandes exactes de lecture/écriture/vérification.
