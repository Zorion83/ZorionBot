# Design — Prises de position scalées (3 paliers) sur le bot v2

**Date :** 2026-09-18
**Statut :** Approuvé
**Branche :** `evolve/meanrev-v2` (bot `donchianbot-v2`, compte démo IG `Raspi_algo02`)

---

## Contexte

Le bot v2 (voir [`2026-09-18-zorionbot-v2-design.md`](./2026-09-18-zorionbot-v2-design.md)) tourne actuellement en copie exacte du bot 1 : un signal → une position → un seul TP. Le propriétaire veut faire évoluer cette stratégie pour capter à la fois les petits retours à la moyenne (rapides, fréquents) et les mouvements plus amples, sans changer le risque total accepté par trade.

Ce chantier **ne touche que le bot v2**. Le bot 1 (`donchianbot`, branche `main`) reste inchangé.

## Objectif

Quand un signal se déclenche, ouvrir **3 positions simultanées** au lieu d'une : même entrée, même SL initial, TP différents. Dès que la première (TP le plus proche) est touchée, remonter le SL des deux positions restantes pour sécuriser la suite du mouvement.

## Décisions validées

| Sujet | Décision |
|---|---|
| Niveaux de TP | TP1 = 1×ATR, TP2 = 2×ATR, TP3 = 3×ATR (SL = 5×ATR, inchangé — à revoir dans ~2 mois) |
| Taille des 3 positions | Égale — chacune risque risk_amount ÷ 3 (≈1.667 % du solde chacune, ≈186 $ actuellement). Si le prix va direct au SL sans toucher aucun TP, la perte totale des 3 = risk_amount (5 %), identique au comportement actuel à position unique |
| Bascule breakeven | Dès que TP1 est touché (position 1 fermée en profit), le SL des positions 2 et 3 passe à **entrée − 0.2×ATR** (LONG) / **entrée + 0.2×ATR** (SHORT) — marge "air" pour ne pas ressortir sur un simple retour bruité au prix d'entrée |
| Visibilité | Chaque position taguée individuellement dans les messages Telegram et le journal (`1/3`, `2/3`, `3/3`) pour pouvoir suivre la performance de chaque palier séparément |
| Export Excel | Fichier de suivi (horodatage, prix, TP, SL, tailles, indicateurs ayant déclenché le signal) — **hors périmètre de ce chantier**, prévu une fois le bot scalé en place et stable |

---

## Architecture

### Faisabilité côté IG (déjà vérifiée dans le code)

`ig_broker.py::_place_order` envoie déjà `forceOpen: true` sur chaque ordre — IG accepte donc plusieurs positions distinctes sur le même epic (GOLD) sans les fusionner. Aucun changement requis côté ouverture d'ordre pour permettre les 3 positions.

Deux capacités manquent et doivent être ajoutées :
1. **Amender le SL d'une position ouverte** sans la fermer (nécessaire pour la bascule breakeven). IG expose un endpoint dédié pour ça (`PUT /positions/otc/{dealId}`) — à implémenter et **vérifier en démo** avant de considérer ce mécanisme fiable, l'implémentation exacte du endpoint n'étant pas encore testée dans ce projet.
2. **Fermer une position précise par `deal_id`**, pas seulement "la position sur cet epic" — `close_position()` prend aujourd'hui un `symbol` et ferme la première position trouvée sur cet epic ; avec 3 positions simultanées sur GOLD, ça doit cibler un `deal_id` précis (utilisé par le time stop, qui s'applique par position individuelle).

### Nouveau module `position_scaling.py`

Isole la logique de scaling du reste (signal detection dans `strategy_meanrev.py` reste inchangé, risk sizing dans `risk.py` reste réutilisé tel quel) :

```python
def build_scaled_orders(signal: dict, risk_amount: float, contract_size: float) -> list[dict]:
    """
    À partir d'un signal (entry, sl_price, direction, atr) et du risque total,
    retourne 3 dicts d'ordre {tier, direction, entry, sl, tp, qty}.
    Chaque tier a le même entry/sl, un TP propre (1/2/3 × ATR),
    qty = (risk_amount / 3) / (sl_dist × contract_size).
    """
```

`analyse_meanrev()` doit exposer la valeur d'ATR utilisée (déjà calculée en interne, juste à retourner dans le dict signal) pour que `build_scaled_orders` puisse dériver TP2/TP3 sans recalculer les indicateurs.

### Suivi des positions — refonte de `_signal_cache` et `_prev_positions`

Aujourd'hui indexés par `epic` (une seule entrée possible par actif). Avec 3 positions simultanées sur le même epic, ça doit passer à une indexation par **`deal_id`** :

```json
{
  "<deal_id>": {
    "epic": "CS.D.CFEGOLD.CEF.IP",
    "asset_name": "GOLD",
    "direction": "BUY",
    "tier": 1,
    "entry": 4350.00,
    "sl": 4300.00,
    "tp": 4360.00,
    "qty": 0.4,
    "opened_at": "2026-09-18T10:00:00Z"
  }
}
```

Pas besoin d'un `group_id` séparé : la contrainte existante (`if epic in open_epics: skip` dans `run_cycle`) garantit qu'un seul groupe de 3 positions est ouvert par actif à la fois — les "frères" d'une position se retrouvent simplement en filtrant le cache par `epic`, à l'exclusion de la position elle-même.

### Détection de clôture et déclenchement du breakeven

Problème identifié en lisant le code existant : `main.py` détecte aujourd'hui une clôture en comparant le **camp** (`"sell" si direction achetée`) sur les transactions IG récentes — ça suffisait avec une position par actif, mais avec 3 positions **de même sens** sur le même actif, le camp seul ne permet plus de savoir laquelle des 3 a clôturé.

Nouvelle logique : pour chaque `deal_id` disparu de `get_open_positions()` par rapport au cycle précédent, chercher parmi les transactions IG récentes (même camp de clôture) celle dont le `close_level` est **le plus proche du TP ou du SL mis en cache pour ce deal_id précis** (chaque palier a un TP distinct, donc pas d'ambiguïté pour identifier un TP1/TP2/TP3). Cas dégénéré accepté : si les positions 2 et 3 se ferment ensemble sur le même SL, l'association exacte entre `deal_id` et transaction peut être approximative dans le journal — sans impact réel puisqu'elles partagent la même taille, le même entry et le même SL (P&L quasi identique).

Une fois une clôture en profit identifiée sur une position de **tier 1** :
1. Journaliser normalement (comme aujourd'hui, avec le tag `tier`).
2. Chercher les autres positions ouvertes du même `epic` dans le cache (tiers 2 et 3 encore actifs).
3. Pour chacune, appeler le nouvel `amend_stop(deal_id, nouveau_sl)` avec `nouveau_sl = entry ∓ 0.2×ATR`.
4. Envoyer un message Telegram confirmant la bascule breakeven.
5. Mettre à jour le cache local (`sl` de ces entrées) pour que le suivi TP/SL affiché en `/status` reste cohérent.

### Journal et Telegram

- `trade_journal.json` : chaque entrée gagne un champ `tier` (1/2/3). Trois trades apparaissent par signal au lieu d'un.
- Messages Telegram (`send_signal`, `send_trade_closed`, `/status`) : préfixés par le tag de palier, ex. `GOLD — Position 2/3 (TP2)`.

---

## Fichiers impactés

| Fichier | Modification |
|---|---|
| `app/strategy_meanrev.py` | Retourner l'ATR utilisé dans le dict signal (pas d'autre changement) |
| `app/position_scaling.py` | **Nouveau** — `build_scaled_orders()` |
| `app/brokers/ig_broker.py` | Nouveau `amend_stop(deal_id, new_sl)` ; `close_position` accepte un `deal_id` |
| `app/brokers/base_broker.py` | Interface étendue en conséquence |
| `app/main.py` | Boucle d'ouverture (3 ordres au lieu d'1), refonte `_signal_cache`/`_prev_positions` par `deal_id`, logique de matching de clôture par prix, déclenchement breakeven, tags de palier dans le journal |
| `app/telegram_notifier.py` | Tags de palier dans les messages |

## Tests

- `position_scaling.py` : tests purs (pas de broker) — 3 tiers correctement dimensionnés, somme des risques = risk_amount, arrondi au pas 0.1 contrat.
- Matching de clôture par prix : cas simple (TP1 seul fermé), cas dégénéré (2 et 3 fermés ensemble sur le même SL).
- `ig_broker.amend_stop` : test avec `httpx` mocké, comme les autres méthodes du broker.
- Suite existante (`pytest tests/`) : doit rester verte, aucune régression sur la détection de signal ni le sizing de base.

## Hors périmètre

- Export Excel des trades (prévu une fois le bot scalé stable — voir décisions validées)
- Ajustement du SL à 5×ATR (reconduit tel quel, revu dans ~2 mois selon le propriétaire)
- Toute modification du bot 1 (`main`, `donchianbot`)
