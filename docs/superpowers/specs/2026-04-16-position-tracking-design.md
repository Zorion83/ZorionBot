# Design — Suivi des positions avec numérotation incrémentale

**Date :** 2026-04-16
**Statut :** Approuvé

---

## Contexte

ZorionBot détecte déjà la fermeture des positions et calcule le P&L, mais rien n'est persisté sur disque. Le résumé quotidien et la commande `/status` affichent les positions ouvertes sans SL, TP ni progression. Il n'existe aucun historique des trades clôturés.

## Objectif

- Positions ouvertes : affichage détaillé (#N, direction, entrée, actuel, P&L, SL, TP, progression %)
- Positions clôturées : historique mensuel persistant avec ID incrémental (#1…#N, reset chaque mois)
- Résumé quotidien : positions ouvertes (détaillées) + trades clôturés du jour
- Nouvelle commande `/trades` : journal mensuel complet

---

## Structures de données

### `bot_state.json` (étendu)

```json
{
  "last_summary": "2026-04-16",
  "open_signal_cache": {
    "BTC/USD": {
      "sl": 81000.0,
      "tp": 88500.0,
      "qty": 0.002,
      "entry": 83500.0,
      "asset_name": "Bitcoin",
      "direction": "BUY",
      "opened_at": "2026-04-16T10:00:00Z"
    }
  }
}
```

- Alimenté lorsqu'un signal se déclenche (ordre placé avec succès)
- Nettoyé lorsque la position est détectée fermée
- Survit aux redémarrages du bot

### `trade_journal.json` (nouveau)

```json
{
  "month": "2026-04",
  "next_id": 3,
  "trades": [
    {
      "id": 1,
      "symbol": "BTC/USD",
      "asset_name": "Bitcoin",
      "direction": "BUY",
      "entry_price": 83500.0,
      "exit_price": 84200.0,
      "sl_price": 81000.0,
      "tp_price": 88500.0,
      "qty": 0.002,
      "pnl": 1.4,
      "closed_at": "2026-04-16T14:30:00Z"
    }
  ]
}
```

**Rotation mensuelle :** au chargement, si `month != YYYY-MM courant` → archive en `trade_journal_YYYY-MM.json`, repart avec `next_id=1` et `trades=[]`.

---

## Format d'affichage

### Position ouverte

```
#1 🚀 LONG BTC/USD
   Entrée  : 83 500.00 → Actuel : 84 200.00
   P&L     : +210.50 $
   SL      : 81 000.00  |  TP : 88 500.00
   Prog.   : ▓▓▓░░░░░░░ 14% vers TP
```

Calcul progression :
- LONG  : `(prix_actuel - entrée) / (TP - entrée) × 100`
- SHORT : `(entrée - prix_actuel) / (entrée - TP) × 100`
- Plafonnée à 100%, minimum 0%

### Trades clôturés du jour (dans résumé quotidien)

```
📋 Trades du jour (2) :
#1 ✅ LONG BTC/USD   | +210.50 $ | 10:30
#2 ❌ SHORT SPY      |  -45.20 $ | 14:00
```

Les numéros (#1, #2) correspondent aux IDs dans le journal mensuel.

### Commande `/trades` (journal mensuel)

```
📒 Trades — Avril 2026 · 3 trades
Win : 2 ✅  Loss : 1 ❌  P&L total : +185.30 $

#1 ✅ LONG  BTC/USD | +210.50 $ | 14/04 10:30
#2 ❌ SHORT SPY     |  -45.20 $ | 15/04 14:00
#3 ✅ LONG  BTC/USD |  +20.00 $ | 16/04 09:00
```

---

## Modifications du code

### `main.py`

**Nouvelles variables globales :**
```python
_signal_cache: dict = {}   # {symbol: {sl, tp, qty, entry, asset_name, direction, opened_at}}
_JOURNAL_FILE = os.path.join(DATA_DIR, "trade_journal.json")
```

**Nouvelles fonctions :**
- `_load_journal() -> dict` : charge depuis disque, applique la rotation mensuelle si nécessaire
- `_save_journal(journal: dict) -> None` : écrit sur disque
- `_rotate_journal_if_needed(journal: dict) -> dict` : archive l'ancien mois si besoin
- `_add_to_journal(symbol, asset_name, direction, entry, exit_price, sl, tp, qty, pnl, closed_at) -> int` : ajoute un trade, retourne son ID

**Modifications `run_cycle()`:**
1. Après placement d'ordre réussi : `_signal_cache[epic] = {sl, tp, qty, entry, ...}` + `_save_state()`
2. Dans le bloc détection clôture : appel `_add_to_journal(...)` + `del _signal_cache[epic]` + `_save_state()`

**Modification `handle_telegram_command()`:**
- Cas `/trades` : charge le journal, formate et envoie
- Cas `/status` : enrichit les positions ouvertes avec SL/TP depuis `_signal_cache`

**Modification appel `send_daily_summary()`:**
- Filtre les trades du journal dont `closed_at` date d'aujourd'hui → passe la liste en paramètre

### `telegram_notifier.py`

**`send_daily_summary()`** — signature étendue :
```python
async def send_daily_summary(
    self,
    trades_today: int,
    open_positions: list,
    closed_today: list,        # nouveau
    signal_cache: dict,        # nouveau — pour SL/TP
) -> None:
```

**Nouvelle fonction helper (module-level) :**
```python
def _format_open_position(idx: int, pos: dict, cache: dict) -> str:
    """Formate une position ouverte avec SL/TP et barre de progression."""
```

---

## Fichiers impactés

| Fichier | Type de modification |
|---------|---------------------|
| `app/main.py` | Ajout signal cache, journal, commande `/trades`, mise à jour clôture |
| `app/telegram_notifier.py` | Extension `send_daily_summary()`, helper format position |
| `app/data/bot_state.json` | Ajout champ `open_signal_cache` |
| `app/data/trade_journal.json` | Nouveau fichier créé au runtime |

---

## Contraintes

- Telegram : limite 4096 caractères par message. Si `/trades` dépasse la limite, tronquer avec `… (+N trades)`.
- Si le signal cache ne contient pas d'entrée pour une position ouverte (position ouverte avant la mise à jour), SL/TP affichés comme `N/A`.
- La rotation mensuelle se fait au premier cycle après minuit le 1er du mois.
