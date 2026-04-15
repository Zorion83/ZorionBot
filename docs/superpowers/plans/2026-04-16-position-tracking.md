# Position Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un journal mensuel persistant des trades clôturés (#ID incrémental), afficher SL/TP et progression sur les positions ouvertes, et exposer tout ça via `/trades`, `/status` et le résumé quotidien Telegram.

**Architecture:** Un `_signal_cache` global (persisté dans `bot_state.json`) stocke SL/TP au moment du signal. Un `_journal` global (fichier `trade_journal.json`) accumule les trades clôturés avec ID mensuel. La détection de clôture existante dans `run_cycle()` est enrichie pour alimenter le journal. Les fonctions d'affichage sont centralisées dans `telegram_notifier.py`.

**Tech Stack:** Python 3.11, asyncio, httpx, JSON files, pytest

---

## File Map

| Fichier | Action | Responsabilité |
|---------|--------|---------------|
| `app/main.py` | Modifier | Globals `_signal_cache` / `_journal`, fonctions journal, signal cache à l'ordre, intégration clôture, commande `/trades` |
| `app/telegram_notifier.py` | Modifier | Helper `_format_open_position()`, extension `send_daily_summary()` |
| `tests/test_journal.py` | Créer | Tests des fonctions journal (rotation, ajout, IDs) |
| `tests/test_telegram_notifier.py` | Modifier | Tests `_format_open_position` et `send_daily_summary` étendu |

---

## Task 1 — Journal helpers dans `main.py`

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_journal.py`

- [ ] **Step 1.1 : Écrire les tests qui échouent**

Créer `tests/test_journal.py` :

```python
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from unittest.mock import patch
from datetime import datetime, timezone


# ── Helpers importés depuis main après monkey-patch du DATA_DIR ──

def _get_journal_fns(tmp_dir):
    """Retourne les fonctions journal avec DATA_DIR patché vers tmp_dir."""
    import importlib
    import main as m
    m.DATA_DIR = tmp_dir
    m._JOURNAL_FILE = os.path.join(tmp_dir, "trade_journal.json")
    # reload pour réinitialiser les globals
    return m._load_journal, m._save_journal, m._add_to_journal, m._rotate_journal_if_needed


class TestJournalRotation:
    def test_no_rotation_same_month(self, tmp_path):
        current = datetime.now(timezone.utc).strftime("%Y-%m")
        journal = {"month": current, "next_id": 2, "trades": [{"id": 1}]}
        journal_file = tmp_path / "trade_journal.json"
        journal_file.write_text(json.dumps(journal))

        import main as m
        m._JOURNAL_FILE = str(journal_file)
        result = m._rotate_journal_if_needed(journal)

        assert result["month"] == current
        assert result["next_id"] == 2          # inchangé
        assert not (tmp_path / "trade_journal_2025-01.json").exists()

    def test_rotation_on_new_month(self, tmp_path):
        old_month = "2025-01"
        journal = {"month": old_month, "next_id": 4, "trades": [{"id": 3}]}

        import main as m
        m.DATA_DIR = str(tmp_path)
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        result = m._rotate_journal_if_needed(journal)

        current = datetime.now(timezone.utc).strftime("%Y-%m")
        assert result["month"] == current
        assert result["next_id"] == 1
        assert result["trades"] == []
        archive = tmp_path / f"trade_journal_{old_month}.json"
        assert archive.exists()
        archived = json.loads(archive.read_text())
        assert archived["month"] == old_month


class TestJournalAddTrade:
    def test_first_trade_gets_id_1(self, tmp_path):
        import main as m
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        journal = {"month": "2026-04", "next_id": 1, "trades": []}

        trade_id = m._add_to_journal(
            journal,
            symbol="BTC/USD", asset_name="Bitcoin", direction="BUY",
            entry_price=83500.0, exit_price=84200.0,
            sl_price=81000.0, tp_price=88500.0,
            qty=0.002, pnl=1.4,
            closed_at="2026-04-16T14:30:00Z",
        )

        assert trade_id == 1
        assert journal["next_id"] == 2
        assert len(journal["trades"]) == 1
        assert journal["trades"][0]["id"] == 1
        assert journal["trades"][0]["symbol"] == "BTC/USD"

    def test_second_trade_gets_id_2(self, tmp_path):
        import main as m
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        journal = {"month": "2026-04", "next_id": 1, "trades": []}

        m._add_to_journal(journal, "BTC/USD", "Bitcoin", "BUY",
                          83500.0, 84200.0, 81000.0, 88500.0, 0.002, 1.4,
                          "2026-04-16T10:00:00Z")
        trade_id = m._add_to_journal(journal, "SPY", "SPY ETF", "SELL",
                                     500.0, 495.0, 505.0, 490.0, 1.0, 5.0,
                                     "2026-04-16T14:00:00Z")

        assert trade_id == 2
        assert journal["next_id"] == 3
        assert len(journal["trades"]) == 2


class TestLoadJournal:
    def test_returns_fresh_journal_when_file_missing(self, tmp_path):
        import main as m
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        journal = m._load_journal()

        current = datetime.now(timezone.utc).strftime("%Y-%m")
        assert journal["month"] == current
        assert journal["next_id"] == 1
        assert journal["trades"] == []

    def test_loads_existing_journal(self, tmp_path):
        current = datetime.now(timezone.utc).strftime("%Y-%m")
        data = {"month": current, "next_id": 5, "trades": [{"id": 4}]}
        jfile = tmp_path / "trade_journal.json"
        jfile.write_text(json.dumps(data))

        import main as m
        m._JOURNAL_FILE = str(jfile)
        journal = m._load_journal()

        assert journal["next_id"] == 5
        assert len(journal["trades"]) == 1
```

- [ ] **Step 1.2 : Vérifier que les tests échouent**

```bash
cd "/Users/remyclaudel/Documents/Developpement/Claude.Cowork/Algo_B&G/DonchianBot"
python3 -m pytest tests/test_journal.py -v 2>&1 | tail -20
```

Attendu : ImportError ou AttributeError (`_rotate_journal_if_needed` non défini).

- [ ] **Step 1.3 : Ajouter les variables et fonctions dans `main.py`**

Dans `main.py`, après le bloc `# ── Bot state persistence`:

```python
# ── Trade journal (historique mensuel) ───────────────────────────
_JOURNAL_FILE = os.path.join(DATA_DIR, "trade_journal.json")
_journal: dict = {}          # chargé dans main()
_signal_cache: dict = {}     # {symbol: {sl, tp, qty, entry, asset_name, direction, opened_at}}


def _rotate_journal_if_needed(journal: dict) -> dict:
    """Si le journal est d'un mois passé, l'archive et retourne un nouveau."""
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    if journal.get("month") == current_month:
        return journal
    old_month = journal.get("month", "unknown")
    archive_path = os.path.join(DATA_DIR, f"trade_journal_{old_month}.json")
    try:
        with open(archive_path, "w") as f:
            json.dump(journal, f, indent=2)
        logger.info("Journal archivé — %s (%d trades)", old_month, len(journal.get("trades", [])))
    except Exception as e:
        logger.warning("Error archiving journal: %s", e)
    return {"month": current_month, "next_id": 1, "trades": []}


def _load_journal() -> dict:
    """Charge le journal depuis le disque, avec rotation mensuelle si nécessaire."""
    default = {"month": datetime.now(timezone.utc).strftime("%Y-%m"), "next_id": 1, "trades": []}
    try:
        if os.path.exists(_JOURNAL_FILE):
            with open(_JOURNAL_FILE) as f:
                data = json.load(f)
            return _rotate_journal_if_needed(data)
    except Exception as e:
        logger.warning("Error reading journal: %s", e)
    return default


def _save_journal(journal: dict) -> None:
    try:
        with open(_JOURNAL_FILE, "w") as f:
            json.dump(journal, f, indent=2)
    except Exception as e:
        logger.warning("Error writing journal: %s", e)


def _add_to_journal(
    journal: dict,
    symbol: str,
    asset_name: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    sl_price: float,
    tp_price: float,
    qty: float,
    pnl: float,
    closed_at: str,
) -> int:
    """Ajoute un trade clôturé au journal. Retourne l'ID assigné."""
    trade_id = journal["next_id"]
    journal["trades"].append({
        "id":          trade_id,
        "symbol":      symbol,
        "asset_name":  asset_name,
        "direction":   direction,
        "entry_price": round(entry_price, 4),
        "exit_price":  round(exit_price, 4),
        "sl_price":    round(sl_price, 4),
        "tp_price":    round(tp_price, 4),
        "qty":         round(qty, 6),
        "pnl":         round(pnl, 2),
        "closed_at":   closed_at,
    })
    journal["next_id"] = trade_id + 1
    return trade_id
```

Also update `_save_state()` to do a **read-modify-write** (merge instead of overwrite) :

```python
def _save_state(updates: dict) -> None:
    try:
        state = _load_state()
        state.update(updates)
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.warning("Error writing state file: %s", e)
```

- [ ] **Step 1.4 : Vérifier que les tests passent**

```bash
python3 -m pytest tests/test_journal.py -v 2>&1 | tail -20
```

Attendu : 6 tests PASSED.

- [ ] **Step 1.5 : Commit**

```bash
cd "/Users/remyclaudel/Documents/Developpement/Claude.Cowork/Algo_B&G/DonchianBot"
git add app/main.py tests/test_journal.py
git commit -m "feat: add trade journal helpers and tests"
```

---

## Task 2 — Chargement du journal et signal cache au démarrage

**Files:**
- Modify: `app/main.py` (fonction `main()`)

- [ ] **Step 2.1 : Charger le journal et le signal cache au démarrage**

Dans `main()`, juste après `_load_disk_cache()` :

```python
    _load_disk_cache()

    global _journal, _signal_cache
    _journal = _load_journal()
    _signal_cache = bot_state.get("open_signal_cache", {})
    logger.info(
        "Journal chargé — %s : %d trade(s) | Signal cache : %d entrée(s)",
        _journal["month"], len(_journal["trades"]), len(_signal_cache),
    )
```

- [ ] **Step 2.2 : Vérifier que le bot démarre sans erreur**

```bash
cd "/Users/remyclaudel/Documents/Developpement/Claude.Cowork/Algo_B&G/DonchianBot"
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Attendu : tous les tests passent.

- [ ] **Step 2.3 : Commit**

```bash
git add app/main.py
git commit -m "feat: load trade journal and signal cache on startup"
```

---

## Task 3 — Alimenter le signal cache à l'émission d'un signal

**Files:**
- Modify: `app/main.py` (bloc `run_cycle()` — placement d'ordre)

- [ ] **Step 3.1 : Sauvegarder SL/TP dans `_signal_cache` après un ordre réussi**

Dans `run_cycle()`, remplacer le bloc de placement d'ordre :

```python
            # Place the order
            try:
                if signal["direction"] == "BUY":
                    await broker.open_long(
                        epic, signal["qty"], signal["sl_price"], signal["tp_price"],
                        comment=f"DonchianBot_{asset_name}",
                        currency_code=asset_config.get("currency_code", "EUR"),
                    )
                else:
                    await broker.open_short(
                        epic, signal["qty"], signal["sl_price"], signal["tp_price"],
                        comment=f"DonchianBot_{asset_name}",
                        currency_code=asset_config.get("currency_code", "EUR"),
                    )
                # ── Mémoriser SL/TP pour affichage futur ─────────
                _signal_cache[epic] = {
                    "sl":         signal["sl_price"],
                    "tp":         signal["tp_price"],
                    "qty":        signal["qty"],
                    "entry":      signal["entry_price"],
                    "asset_name": asset_name,
                    "direction":  signal["direction"],
                    "opened_at":  now.isoformat(),
                }
                _save_state({"open_signal_cache": _signal_cache})
                await telegram.send_signal(signal, DEMO_MODE)

            except BrokerError as e:
                logger.error("BrokerError %s: %s", asset_name, e)
                await telegram.send_error(f"Order {asset_name}", str(e))
```

- [ ] **Step 3.2 : Vérifier les tests**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Attendu : tous les tests passent (pas de régression).

- [ ] **Step 3.3 : Commit**

```bash
git add app/main.py
git commit -m "feat: populate signal cache with SL/TP on order placement"
```

---

## Task 4 — Intégrer la clôture de position dans le journal

**Files:**
- Modify: `app/main.py` (bloc "Detect closed positions" dans `run_cycle()`)

- [ ] **Step 4.1 : Appeler `_add_to_journal` quand une position se ferme**

Dans `run_cycle()`, remplacer le bloc qui calcule le P&L et appelle `send_trade_closed` :

```python
                if closing_fill:
                    exit_price  = closing_fill["filled_avg_price"]
                    entry_price = pos_data["entry_price"]
                    qty         = pos_data["qty"]
                    if pos_data["direction"] == "BUY":
                        pnl = (exit_price - entry_price) * qty
                    else:
                        pnl = (entry_price - exit_price) * qty
                    logger.info(
                        "Trade closed — %s %s | entry=%.2f exit=%.2f P&L=%.2f",
                        pos_data["direction"], symbol, entry_price, exit_price, pnl
                    )
                    await telegram.send_trade_closed(symbol, pos_data["direction"], pnl, DEMO_MODE)

                    # ── Enregistrer dans le journal mensuel ───────
                    cache_entry = _signal_cache.pop(symbol, {})
                    _add_to_journal(
                        _journal,
                        symbol      = symbol,
                        asset_name  = cache_entry.get("asset_name", symbol),
                        direction   = pos_data["direction"],
                        entry_price = entry_price,
                        exit_price  = exit_price,
                        sl_price    = cache_entry.get("sl", 0.0),
                        tp_price    = cache_entry.get("tp", 0.0),
                        qty         = qty,
                        pnl         = pnl,
                        closed_at   = now.isoformat(),
                    )
                    _save_journal(_journal)
                    _save_state({"open_signal_cache": _signal_cache})
```

- [ ] **Step 4.2 : Vérifier les tests**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Attendu : tous les tests passent.

- [ ] **Step 4.3 : Commit**

```bash
git add app/main.py
git commit -m "feat: record closed trades in monthly journal"
```

---

## Task 5 — Helper `_format_open_position` dans `telegram_notifier.py`

**Files:**
- Modify: `app/telegram_notifier.py`
- Modify: `tests/test_telegram_notifier.py`

- [ ] **Step 5.1 : Écrire les tests qui échouent**

Ajouter à la fin de `tests/test_telegram_notifier.py` :

```python
class TestFormatOpenPosition:
    def _make_pos(self, direction="BUY", entry=83500.0, current=84200.0, pnl=210.5):
        return {
            "epic":          "BTC/USD",
            "direction":     direction,
            "entry_price":   entry,
            "current_price": current,
            "unrealized_pl": pnl,
        }

    def test_shows_number_and_symbol(self):
        from telegram_notifier import _format_open_position
        result = _format_open_position(1, self._make_pos(), cache_entry=None)
        assert "#1" in result
        assert "BTC/USD" in result

    def test_long_label(self):
        from telegram_notifier import _format_open_position
        result = _format_open_position(1, self._make_pos("BUY"), cache_entry=None)
        assert "LONG" in result

    def test_short_label(self):
        from telegram_notifier import _format_open_position
        result = _format_open_position(1, self._make_pos("SELL"), cache_entry=None)
        assert "SHORT" in result

    def test_no_cache_shows_na(self):
        from telegram_notifier import _format_open_position
        result = _format_open_position(1, self._make_pos(), cache_entry=None)
        assert "N/A" in result

    def test_cache_shows_sl_tp(self):
        from telegram_notifier import _format_open_position
        cache = {"sl": 81000.0, "tp": 88500.0, "direction": "BUY"}
        result = _format_open_position(1, self._make_pos(), cache_entry=cache)
        assert "81000" in result
        assert "88500" in result

    def test_long_progress_calculation(self):
        from telegram_notifier import _format_open_position
        # entry=0, current=5, tp=10 → 50%
        pos   = self._make_pos(entry=0.0, current=5.0)
        cache = {"sl": -1.0, "tp": 10.0, "direction": "BUY"}
        result = _format_open_position(1, pos, cache_entry=cache)
        assert "50%" in result

    def test_short_progress_calculation(self):
        from telegram_notifier import _format_open_position
        # entry=10, current=5, tp=0 → 50%
        pos   = self._make_pos("SELL", entry=10.0, current=5.0, pnl=5.0)
        cache = {"sl": 11.0, "tp": 0.0, "direction": "SELL"}
        result = _format_open_position(1, pos, cache_entry=cache)
        assert "50%" in result

    def test_progress_capped_at_100(self):
        from telegram_notifier import _format_open_position
        # current déjà au-delà du TP
        pos   = self._make_pos(entry=0.0, current=15.0)
        cache = {"sl": -1.0, "tp": 10.0, "direction": "BUY"}
        result = _format_open_position(1, pos, cache_entry=cache)
        assert "100%" in result
```

- [ ] **Step 5.2 : Vérifier que les tests échouent**

```bash
python3 -m pytest tests/test_telegram_notifier.py::TestFormatOpenPosition -v 2>&1 | tail -15
```

Attendu : ImportError (`cannot import name '_format_open_position'`).

- [ ] **Step 5.3 : Ajouter `_format_open_position` dans `telegram_notifier.py`**

Ajouter juste avant la classe `TelegramNotifier` (après les imports) :

```python
def _format_open_position(idx: int, pos: dict, cache_entry: dict | None) -> str:
    """
    Formate une position ouverte avec numéro, SL/TP et barre de progression.

    Args:
        idx:         Numéro d'affichage (1, 2, 3…)
        pos:         Dict retourné par get_open_positions() —
                     clés : epic, direction, entry_price, current_price, unrealized_pl
        cache_entry: Dict depuis _signal_cache — clés : sl, tp, direction
                     None si la position a été ouverte avant la mise à jour du bot.
    """
    direction = "🚀 LONG" if pos["direction"] == "BUY" else "🔻 SHORT"
    pnl       = pos.get("unrealized_pl", 0.0)
    pnl_str   = f"{'+'if pnl >= 0 else ''}{pnl:.2f} $"
    entry     = pos.get("entry_price", 0.0)
    current   = pos.get("current_price", 0.0)

    lines = [
        f"<b>#{idx} {direction} {pos['epic']}</b>",
        f"   Entrée  : {entry:.2f} → Actuel : {current:.2f}",
        f"   P&amp;L  : {pnl_str}",
    ]

    if cache_entry:
        sl = cache_entry.get("sl", 0.0)
        tp = cache_entry.get("tp", 0.0)
        lines.append(f"   SL      : {sl:.2f}  |  TP : {tp:.2f}")
        if tp != entry:
            if pos["direction"] == "BUY":
                prog = (current - entry) / (tp - entry) * 100.0
            else:
                prog = (entry - current) / (entry - tp) * 100.0
            prog    = max(0.0, min(100.0, prog))
            filled  = int(prog / 10)
            bar     = "▓" * filled + "░" * (10 - filled)
            lines.append(f"   Prog.   : {bar} {prog:.0f}% vers TP")
    else:
        lines.append("   SL/TP  : N/A")

    return "\n".join(lines)
```

- [ ] **Step 5.4 : Vérifier que les tests passent**

```bash
python3 -m pytest tests/test_telegram_notifier.py::TestFormatOpenPosition -v 2>&1 | tail -15
```

Attendu : 8 tests PASSED.

- [ ] **Step 5.5 : Commit**

```bash
git add app/telegram_notifier.py tests/test_telegram_notifier.py
git commit -m "feat: add _format_open_position helper with SL/TP and progress bar"
```

---

## Task 6 — Mettre à jour `send_daily_summary()`

**Files:**
- Modify: `app/telegram_notifier.py`
- Modify: `tests/test_telegram_notifier.py`

- [ ] **Step 6.1 : Écrire le test qui échoue**

Ajouter à `tests/test_telegram_notifier.py` :

```python
class TestSendDailySummaryExtended:
    def test_closed_today_section_appears(self):
        """send_daily_summary doit afficher la section trades clôturés si non vide."""
        t = TelegramNotifier("token", "chat")
        captured = []
        async def fake_send(text): captured.append(text)
        t._send = fake_send

        closed_today = [
            {"id": 1, "symbol": "BTC/USD", "direction": "BUY",
             "pnl": 210.5, "closed_at": "2026-04-16T10:30:00Z"},
        ]
        open_positions = []
        signal_cache   = {}
        asyncio.run(t.send_daily_summary(1, open_positions, closed_today, signal_cache))

        assert len(captured) == 1
        assert "#1" in captured[0]
        assert "BTC/USD" in captured[0]
        assert "+210.50" in captured[0]

    def test_no_closed_today_section_when_empty(self):
        """Pas de section clôtures si aucun trade aujourd'hui."""
        t = TelegramNotifier("token", "chat")
        captured = []
        async def fake_send(text): captured.append(text)
        t._send = fake_send

        asyncio.run(t.send_daily_summary(0, [], [], {}))
        assert "clôturés" not in captured[0]

    def test_open_positions_use_format_helper(self):
        """Les positions ouvertes passent par _format_open_position."""
        t = TelegramNotifier("token", "chat")
        captured = []
        async def fake_send(text): captured.append(text)
        t._send = fake_send

        pos = {
            "epic": "BTC/USD", "direction": "BUY",
            "entry_price": 83500.0, "current_price": 84200.0, "unrealized_pl": 210.5,
        }
        cache = {"sl": 81000.0, "tp": 88500.0, "direction": "BUY"}
        asyncio.run(t.send_daily_summary(0, [pos], [], {"BTC/USD": cache}))
        assert "#1" in captured[0]
        assert "81000" in captured[0]   # SL visible
```

- [ ] **Step 6.2 : Vérifier que les tests échouent**

```bash
python3 -m pytest tests/test_telegram_notifier.py::TestSendDailySummaryExtended -v 2>&1 | tail -10
```

Attendu : TypeError (signature incompatible avec ancienne `send_daily_summary`).

- [ ] **Step 6.3 : Remplacer `send_daily_summary` dans `telegram_notifier.py`**

Remplacer la méthode existante :

```python
    async def send_daily_summary(
        self,
        trades_today:   int,
        open_positions: list,
        closed_today:   list,
        signal_cache:   dict,
    ) -> None:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%d/%m/%Y")

        lines = [
            f"📊 <b>DonchianBot — Résumé du {today}</b>",
            f"Trades du jour : {trades_today}",
        ]

        if open_positions:
            lines.append(f"\n<b>Positions ouvertes ({len(open_positions)}) :</b>")
            for idx, pos in enumerate(open_positions, 1):
                cache_entry = signal_cache.get(pos["epic"])
                lines.append(_format_open_position(idx, pos, cache_entry))
        else:
            lines.append("Aucune position ouverte")

        if closed_today:
            lines.append(f"\n<b>Trades clôturés aujourd'hui ({len(closed_today)}) :</b>")
            for t in closed_today:
                emoji  = "✅" if t["pnl"] >= 0 else "❌"
                d_str  = "LONG" if t["direction"] == "BUY" else "SHORT"
                pnl_s  = f"{'+'if t['pnl'] >= 0 else ''}{t['pnl']:.2f} $"
                time_s = t["closed_at"][11:16]
                lines.append(f"#{t['id']} {emoji} {d_str} {t['symbol']} | {pnl_s} | {time_s}")

        await self._send("\n".join(lines))
```

- [ ] **Step 6.4 : Mettre à jour l'appel dans `main.py`**

Dans `main()`, remplacer :

```python
                if now.hour == 8 and now.minute < 31 and last_summary != today_str:
                    positions = await broker.get_open_positions()
                    await telegram.send_daily_summary(trades_today, positions)
                    last_summary = today_str
                    trades_today = 0
                    _save_state({"last_summary": last_summary})
```

Par :

```python
                if now.hour == 8 and now.minute < 31 and last_summary != today_str:
                    positions    = await broker.get_open_positions()
                    closed_today = [
                        t for t in _journal.get("trades", [])
                        if t["closed_at"][:10] == today_str
                    ]
                    await telegram.send_daily_summary(
                        trades_today, positions, closed_today, _signal_cache
                    )
                    last_summary = today_str
                    trades_today = 0
                    _save_state({"last_summary": last_summary})
```

- [ ] **Step 6.5 : Vérifier tous les tests**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Attendu : tous les tests passent.

- [ ] **Step 6.6 : Commit**

```bash
git add app/telegram_notifier.py app/main.py tests/test_telegram_notifier.py
git commit -m "feat: extend send_daily_summary with closed trades and SL/TP positions"
```

---

## Task 7 — Commandes `/trades` et `/status` mises à jour

**Files:**
- Modify: `app/main.py` (fonction `handle_telegram_command`)

- [ ] **Step 7.1 : Ajouter la commande `/trades`**

Dans `handle_telegram_command()`, ajouter après le bloc `/resume` :

```python
    elif command == "/trades":
        try:
            trades = _journal.get("trades", [])
            month  = _journal.get("month", "")

            if not trades:
                await telegram._send("📒 Aucun trade enregistré ce mois-ci.")
                return

            wins      = sum(1 for t in trades if t["pnl"] >= 0)
            losses    = len(trades) - wins
            total_pnl = sum(t["pnl"] for t in trades)
            pnl_str   = f"{'+'if total_pnl >= 0 else ''}{total_pnl:.2f} $"

            month_names = {
                "01": "Janvier", "02": "Février", "03": "Mars", "04": "Avril",
                "05": "Mai", "06": "Juin", "07": "Juillet", "08": "Août",
                "09": "Septembre", "10": "Octobre", "11": "Novembre", "12": "Décembre",
            }
            year, mo  = (month.split("-") + [""])[:2]
            month_str = f"{month_names.get(mo, mo)} {year}"

            lines = [
                f"📒 <b>Trades — {month_str} · {len(trades)} trade(s)</b>",
                f"Win : {wins} ✅  Loss : {losses} ❌  P&amp;L total : {pnl_str}",
                "",
            ]
            for t in trades:
                emoji  = "✅" if t["pnl"] >= 0 else "❌"
                d_str  = "LONG " if t["direction"] == "BUY" else "SHORT"
                pnl_s  = f"{'+'if t['pnl'] >= 0 else ''}{t['pnl']:.2f} $"
                date_s = t["closed_at"][8:10] + "/" + t["closed_at"][5:7] + " " + t["closed_at"][11:16]
                lines.append(f"#{t['id']} {emoji} {d_str} {t['symbol']} | {pnl_s} | {date_s}")

            text = "\n".join(lines)
            if len(text) > 4000:
                header  = "\n".join(lines[:3])
                tail    = []
                for line in reversed(lines[3:]):
                    if len(header) + len("\n".join(tail)) + len(line) + 30 < 4000:
                        tail.insert(0, line)
                    else:
                        break
                skipped = len(trades) - len(tail)
                text    = header + f"\n… (+{skipped} plus anciens)\n" + "\n".join(tail)

            await telegram._send(text)
        except Exception as e:
            await telegram._send(f"❌ Erreur /trades : {e}")
```

- [ ] **Step 7.2 : Mettre à jour `/status` pour afficher SL/TP**

D'abord, mettre à jour l'import en tête de `main.py` :

```python
from telegram_notifier import TelegramNotifier, _format_open_position
```

Puis dans `handle_telegram_command()`, remplacer le bloc `/status` — section positions ouvertes :

```python
            if positions:
                lines.append(f"\n📈 <b>Positions ({len(positions)}) :</b>")
                for idx, p in enumerate(positions, 1):
                    cache_entry = _signal_cache.get(p["epic"])
                    lines.append(_format_open_position(idx, p, cache_entry))
            else:
                lines.append("\n📊 Aucune position ouverte")
```

- [ ] **Step 7.3 : Ajouter `/trades` dans le message `/help`**

Remplacer le texte du `/help` :

```python
        await telegram._send(
            "🤖 <b>DonchianBot — Commandes</b>\n\n"
            "/status  — Solde, positions (SL/TP/progression)\n"
            "/trades  — Journal mensuel des trades clôturés\n"
            "/logs    — Dernières lignes de log\n"
            "/pause   — Suspendre les nouveaux ordres\n"
            "/resume  — Reprendre les signaux\n"
            "/help    — Afficher ce message"
        )
```

- [ ] **Step 7.4 : Vérifier tous les tests**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Attendu : tous les tests passent.

- [ ] **Step 7.5 : Commit**

```bash
git add app/main.py
git commit -m "feat: add /trades command and update /status with SL/TP display"
```

---

## Task 8 — Déploiement sur la Raspi

**Files:** aucun (déploiement)

- [ ] **Step 8.1 : Copier les fichiers modifiés**

```bash
scp "/Users/remyclaudel/Documents/Developpement/Claude.Cowork/Algo_B&G/DonchianBot/app/main.py" \
    raspi-home:DonchianBot/app/main.py

scp "/Users/remyclaudel/Documents/Developpement/Claude.Cowork/Algo_B&G/DonchianBot/app/telegram_notifier.py" \
    raspi-home:DonchianBot/app/telegram_notifier.py
```

- [ ] **Step 8.2 : Rebuild et redémarrage**

```bash
ssh raspi-home "cd ~/DonchianBot && docker compose build 2>&1 | tail -5 && docker compose up -d --force-recreate 2>&1 | tail -5"
```

- [ ] **Step 8.3 : Vérifier les logs de démarrage**

```bash
ssh raspi-home "sleep 5 && docker logs donchianbot 2>&1 | tail -15"
```

Attendu (lignes clés) :
```
Disk cache loaded — 3 assets
Bot state loaded — last_summary: ...
Journal chargé — 2026-04 : 0 trade(s) | Signal cache : 0 entrée(s)
Écoute des commandes Telegram démarrée
Next scan in ...
```

- [ ] **Step 8.4 : Test de fumée — envoyer `/trades` depuis Telegram**

Envoyer `/trades` depuis le chat Telegram configuré.

Attendu : `📒 Aucun trade enregistré ce mois-ci.`

- [ ] **Step 8.5 : Test de fumée — envoyer `/status` depuis Telegram**

Envoyer `/status`.

Attendu : message avec balance, positions ouvertes avec `#N 🚀 LONG ... SL/TP : N/A` (puisque aucun signal n'a encore été placé avec le nouveau cache), ou positions avec SL/TP si un signal a été émis depuis le déploiement.
