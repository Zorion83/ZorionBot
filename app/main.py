#!/usr/bin/env python3
"""
main.py — Trading bot main loop
Strategy : Mean Reversion XAUUSD v5 (BROKER=ig) ou Donchian V1.1 (BROKER=alpaca)
Timeframe: M30
"""
import asyncio
import json
import logging
import logging.handlers
import math
import os
from datetime import datetime, timezone

from config import (
    BROKER, ALPACA_API_KEY, ALPACA_API_SECRET, DEMO_MODE,
    IG_API_KEY, IG_IDENTIFIER, IG_PASSWORD,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID,
    RISK_PCT, DONCHIAN_LENGTH, LOOKBACK_CANDLES,
    POINT_VALUE, RR_RATIO,
    MR_BB_LEN, MR_BB_STD, MR_RSI_LEN, MR_RSI_LO, MR_EMA_LEN, MR_ATR_LEN,
    MR_TP_ATR, MR_SL_ATR, MR_TIME_STOP, MR_SESS_START, MR_SESS_END,
    MR_BREAKEVEN_BUFFER_ATR,
    LOG_FILE, LOG_LEVEL, DATA_DIR,
)
from assets_config import ENABLED_ASSETS
from brokers.alpaca_broker import AlpacaBroker
from brokers.ig_broker import IGBroker
from brokers.base_broker import BrokerError
from strategy import analyse_asset
from strategy_meanrev import analyse_meanrev
from position_scaling import build_scaled_orders
from telegram_notifier import TelegramNotifier, _format_open_position, PIP_REMINDER

# ── Logging ───────────────────────────────────────────────────────
os.makedirs(DATA_DIR, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        # Rotation : sans elle le fichier grossit sans fin (81 Mo constatés le 2026-08-23).
        # Mêmes bornes que le driver json-file du compose : 10 Mo x 3.
        logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)

# httpx logge chaque requête en INFO, URL complète comprise. Le long-polling Telegram
# tourne toutes les 30 s, ce qui (1) écrivait le token du bot en clair dans chaque ligne
# et (2) représentait l'essentiel du volume de log. WARNING garde les erreurs réseau.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("ZorionBot")

# ── Candle cache ──────────────────────────────────────────────────
_candle_cache: dict = {}
_startup_done: set  = set()
_CACHE_FILE = os.path.join(DATA_DIR, "candle_cache.json")

# ── Bot state persistence (daily summary dedup) ───────────────────
_STATE_FILE = os.path.join(DATA_DIR, "bot_state.json")


def _load_state() -> dict:
    try:
        if os.path.exists(_STATE_FILE):
            with open(_STATE_FILE) as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Error reading state file: %s", e)
    return {}


def _save_state(updates: dict) -> None:
    try:
        state = _load_state()
        state.update(updates)
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.warning("Error writing state file: %s", e)

# ── Trade journal (historique mensuel) ───────────────────────────
_JOURNAL_FILE = os.path.join(DATA_DIR, "trade_journal.json")
_journal: dict = {}          # chargé dans main()
# IG : {deal_id: {epic, sl, tp, qty, entry, tier, asset_name, direction, atr, opened_at}}
# Alpaca (legacy) : {epic: {sl, tp, qty, entry, asset_name, direction, opened_at}}
_signal_cache: dict = {}


def _rotate_journal_if_needed(journal: dict) -> dict:
    """Si le journal est d'un mois passé, l'archive et retourne un nouveau."""
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    if journal.get("month") == current_month:
        return journal
    old_month = journal.get("month", "unknown")
    archive_path = os.path.join(os.path.dirname(_JOURNAL_FILE), f"trade_journal_{old_month}.json")
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
        os.makedirs(os.path.dirname(_JOURNAL_FILE), exist_ok=True)
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
    tier: int = 0,
    trade_no: int | None = None,
) -> int:
    """Ajoute un trade clôturé au journal. Retourne l'ID (mensuel) assigné."""
    trade_id = journal["next_id"]
    trade = {
        "id":          trade_id,
        "symbol":      symbol,
        "asset_name":  asset_name,
        "tier":        tier,
        "direction":   direction,
        "entry_price": round(entry_price, 4),
        "exit_price":  round(exit_price, 4),
        "sl_price":    round(sl_price, 4),
        "tp_price":    round(tp_price, 4),
        "qty":         round(qty, 6),
        "pnl":         round(pnl, 2),
        "closed_at":   closed_at,
    }
    if trade_no is not None:
        trade["trade_no"] = trade_no
    journal["trades"].append(trade)
    journal["next_id"] = trade_id + 1
    return trade_id


def _allocate_trade_no() -> int:
    """Numéro de trade global, attribué à l'ouverture et jamais remis à zéro (contrairement
    à l'id mensuel du journal) : c'est lui qu'on retrouve dans chaque message Telegram."""
    trade_no = int(_load_state().get("next_trade_no", 1))
    _save_state({"next_trade_no": trade_no + 1})
    return trade_no


def _adopt_unknown_positions(open_positions: list) -> list:
    """Reprend dans _signal_cache les positions IG que le bot ne connaît pas.

    Cas typique : /confirms a échoué à l'ouverture, l'ordre est exécuté mais le bot
    n'a pas le dealId. Sans adoption, le trade était journalisé sans SL/TP, avec l'epic
    comme nom d'actif (donc invisible dans le journal web, qui filtre sur "GOLD").
    Retourne les entrées ajoutées.
    """
    adopted = []
    for p in open_positions:
        if p["deal_id"] in _signal_cache:
            continue
        asset_name = next(
            (name for name, cfg in ENABLED_ASSETS.items() if cfg["symbol"] == p["epic"]),
            p["epic"],
        )
        entry = {
            "epic":       p["epic"],
            "asset_name": asset_name,
            "direction":  p["direction"],
            "tier":       1,
            "entry":      p.get("entry_price", 0.0),
            "sl":         p.get("sl") or 0.0,
            "tp":         p.get("tp") or 0.0,
            "qty":        p.get("size", 0.0),
            "opened_at":  p.get("created_at", ""),
            "trade_no":   _allocate_trade_no(),
            "adopted":    True,
        }
        _signal_cache[p["deal_id"]] = entry
        adopted.append(entry)
    return adopted

# ── Previous signal tracking (anti-doublon) ───────────────────────
_prev_long:  dict = {}   # {epic: bool}
_prev_short: dict = {}   # {epic: bool}

# ── Position tracking (closed trade detection) ────────────────────
# IG : {deal_id: {epic, direction, entry_price, qty}} — Alpaca (legacy) : {epic: {direction, entry_price, qty}}
_prev_positions: dict = {}
_last_cycle_iso: str  = ""   # ISO timestamp of last cycle (for order lookup)

# ── Pause / commandes Telegram ────────────────────────────────────
_paused: bool = False         # True = cycles tournent mais ordres bloqués

# ── Cooldown après échec d'ordre (évite le spam de retries) ───────
_order_failure_cooldown: dict = {}   # {epic: iso_timestamp du dernier échec}
_ORDER_FAILURE_COOLDOWN_MINUTES = 120   # 4 cycles avant nouvelle tentative


def _load_disk_cache() -> None:
    if not os.path.exists(_CACHE_FILE):
        return
    try:
        with open(_CACHE_FILE) as f:
            data = json.load(f)
        for epic, entry in data.items():
            _candle_cache[epic] = entry["candles"]
        logger.info("Disk cache loaded — %d assets", len(_candle_cache))
    except Exception as e:
        logger.warning("Error reading disk cache: %s", e)


def _save_disk_cache() -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        data = {epic: {"candles": c} for epic, c in _candle_cache.items()}
        with open(_CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning("Error writing disk cache: %s", e)


def _merge_candles(existing: list, incoming: list) -> list:
    """Fusionne deux listes de bougies par timestamp, la version fraîche l'emportant.

    IG renvoie la bougie en cours dès qu'elle s'ouvre. Comme le cycle tourne 5 s après
    la demi-heure, cette bougie arrive quasi vide (open ≈ high ≈ low ≈ close) : il faut
    la réécrire aux cycles suivants, une fois sa période close. Sans cela chaque barre
    reste figée sur son premier instantané et l'ATR est sous-évalué d'environ 37 %.
    """
    by_time = {c["time"]: c for c in existing}
    by_time.update({c["time"]: c for c in incoming})
    return [by_time[t] for t in sorted(by_time)]


def _refetch_start(candles: list, back: int = 3) -> str:
    """Timestamp à partir duquel redemander les bougies : on remonte de `back` barres
    pour réécrire les dernières (dont la barre en cours) et rattraper un cycle manqué."""
    if not candles:
        return ""
    return candles[-min(back, len(candles))]["time"]


async def get_fresh_candles(broker: AlpacaBroker, epic: str) -> list:
    """3-level candle cache: full fetch → catch-up → incremental."""
    if epic not in _candle_cache:
        # Level 1: full initial fetch
        try:
            candles = await broker.get_candles(epic, LOOKBACK_CANDLES)
            _candle_cache[epic] = candles
            _startup_done.add(epic)
            _save_disk_cache()
            logger.info("Cache initialised — %s: %d candles", epic, len(candles))
        except BrokerError as e:
            if e.status_code == 403:
                logger.warning("Alpaca quota exceeded for %s — asset skipped", epic)
                return []
            raise

    elif epic not in _startup_done:
        # Level 2: catch-up after disk cache load — fetch from last known bar onwards
        try:
            existing   = _candle_cache[epic]
            last_start = _refetch_start(existing)
            new_candles = await broker.get_candles(epic, 1000, start=last_start)
            _startup_done.add(epic)
            if new_candles:
                known_times = {c["time"] for c in existing}
                added       = [c for c in new_candles if c["time"] not in known_times]
                merged      = _merge_candles(existing, new_candles)
                if merged != existing:
                    _candle_cache[epic] = merged[-LOOKBACK_CANDLES:]
                    _save_disk_cache()
                    logger.info("Cache caught up — %s: +%d candle(s), %d réécrite(s)",
                                epic, len(added), len(new_candles) - len(added))
                else:
                    logger.info("Cache caught up — %s (already up to date)", epic)
            else:
                logger.info("Cache caught up — %s (no new data)", epic)
        except BrokerError as e:
            if e.status_code == 403:
                logger.warning("Quota exceeded for %s — using disk cache", epic)
                _startup_done.add(epic)
            else:
                raise

    else:
        # Level 3: incremental update — fetch from last known bar onwards
        try:
            existing   = _candle_cache[epic]
            last_start = _refetch_start(existing)
            new_candles = await broker.get_candles(epic, 3, start=last_start)
            if new_candles:
                known_times = {c["time"] for c in existing}
                added       = [c for c in new_candles if c["time"] not in known_times]
                merged      = _merge_candles(existing, new_candles)
                if merged != existing:
                    _candle_cache[epic] = merged[-LOOKBACK_CANDLES:]
                    _save_disk_cache()
                    logger.info("Cache updated — %s: +%d candle(s), %d réécrite(s)",
                                epic, len(added), len(new_candles) - len(added))
        except BrokerError as e:
            if e.status_code == 403:
                logger.warning("Quota exceeded for %s — analysing from cache", epic)
            else:
                raise

    return _candle_cache.get(epic, [])


def _match_closed_deal(direction: str, cache_entry: dict, candidates: list) -> dict | None:
    """
    Trouve, parmi `candidates` (sortie de get_closed_orders_since), la transaction
    qui correspond le mieux à une position disparue de get_open_positions(), en
    comparant le prix de clôture au TP/SL mis en cache pour CE deal_id précis.

    Chaque palier (tier) a un TP distinct, donc identification fiable pour repérer
    lequel a touché son TP. Cas dégénéré accepté : si 2 positions se ferment ensemble
    sur le même SL, la fonction retourne l'une des deux candidates équidistantes —
    sans impact financier réel puisqu'elles partagent taille/entry/SL (voir spec).
    """
    closing_side = "sell" if direction == "BUY" else "buy"
    same_side = [c for c in candidates if c["side"] == closing_side]
    if not same_side:
        return None

    tp, sl = cache_entry.get("tp", 0.0), cache_entry.get("sl", 0.0)

    def distance(c: dict) -> float:
        level = c["filled_avg_price"]
        refs = [abs(level - ref) for ref in (tp, sl) if ref]
        return min(refs) if refs else float("inf")

    return min(same_side, key=distance)


async def _apply_breakeven(
    broker: IGBroker,
    telegram: TelegramNotifier,
    epic: str,
    closed_deal_id: str,
    cache_entry: dict,
    open_deal_ids: set,
) -> None:
    """TP1 touché : remonte le SL des positions sœurs (même epic) encore ouvertes.

    `open_deal_ids` doit être l'ensemble des deal_id réellement ouverts CE cycle
    (ex. current_deal_ids) — sans ça, quand plusieurs paliers se ferment le même
    cycle (time stop, ou prix qui traverse TP1→TP2→TP3 dans la même bougie), le
    palier 1 (traité en premier) tenterait d'amender le SL de paliers 2/3 déjà
    clôturés côté broker, ce qu'IG rejette (voir revue finale #3).
    """
    entry   = cache_entry.get("entry", 0.0)
    atr_val = cache_entry.get("atr", 0.0)
    if not entry or not atr_val:
        logger.warning(
            "Breakeven abandonné — cache_entry incomplet pour %s (deal_id=%s, entry=%s, atr=%s)",
            epic, closed_deal_id, entry, atr_val,
        )
        return

    direction = cache_entry.get("direction", "BUY")
    sign      = 1 if direction == "BUY" else -1
    new_sl    = entry - sign * MR_BREAKEVEN_BUFFER_ATR * atr_val

    siblings = [
        (deal_id, entry_data) for deal_id, entry_data in _signal_cache.items()
        if entry_data.get("epic") == epic
        and deal_id != closed_deal_id
        and deal_id in open_deal_ids
    ]
    if not siblings:
        return

    amended = False
    for deal_id, entry_data in siblings:
        try:
            await broker.amend_stop(deal_id, new_sl, tp=entry_data.get("tp"))
            entry_data["sl"] = new_sl
            amended = True
            logger.info(
                "Breakeven appliqué — deal_id=%s (tier %s) → SL=%.2f",
                deal_id, entry_data.get("tier"), new_sl,
            )
        except BrokerError as e:
            logger.error("Échec amend_stop breakeven deal_id=%s: %s", deal_id, e)
            await telegram.send_error(f"Breakeven {epic}", str(e))

    if amended:
        _save_state({"open_signal_cache": _signal_cache})
        await telegram._send(
            f"🔒 <b>{epic}</b> — TP1 touché, SL des positions restantes remonté "
            f"au breakeven ({new_sl:.2f})"
        )


async def handle_telegram_command(
    command: str,
    args: list,
    broker: AlpacaBroker,
    telegram: TelegramNotifier,
) -> None:
    """Gère les commandes reçues via Telegram."""
    global _paused

    if command == "/help":
        await telegram._send(
            "🤖 <b>ZorionBot — Commandes</b>\n\n"
            "/status  — Solde, positions (SL/TP/progression)\n"
            "/trades  — Journal mensuel des trades clôturés\n"
            "/logs    — Dernières lignes de log\n"
            "/pause   — Suspendre les nouveaux ordres\n"
            "/resume  — Reprendre les signaux\n"
            "/help    — Afficher ce message"
        )

    elif command == "/status":
        try:
            balance   = await broker.get_account_balance()
            positions = await broker.get_open_positions()
            now_str   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            risk_amt  = round(balance * RISK_PCT, 2)
            mode_tag  = "[DEMO] " if DEMO_MODE else ""

            lines = [
                f"🤖 <b>{mode_tag}ZorionBot</b>",
                f"⏰ {now_str}",
                f"💰 Balance   : ${balance:,.2f}",
                f"🎯 Risk/trade : ${risk_amt:.2f} ({RISK_PCT * 100:.1f}%)",
                f"⏸ Pause     : {'OUI ⚠️' if _paused else 'non'}",
            ]
            if positions:
                lines.append(f"\n📈 <b>Positions ({len(positions)}) :</b>")
                for idx, p in enumerate(positions, 1):
                    # deal_id-keyed sur IG, epic-keyé sur Alpaca (legacy) — au plus
                    # un des deux .get() trouvera quelque chose (voir revue finale #2).
                    cache_entry = _signal_cache.get(p["deal_id"]) or _signal_cache.get(p["epic"])
                    lines.append(_format_open_position(idx, p, cache_entry))
                lines.append(PIP_REMINDER)
            else:
                lines.append("\n📊 Aucune position ouverte")
            await telegram._send("\n".join(lines))
        except Exception as e:
            await telegram._send(f"❌ Erreur /status : {e}")

    elif command == "/logs":
        try:
            n = int(args[0]) if args else 20
            n = min(max(n, 5), 50)
            with open(LOG_FILE, encoding="utf-8") as f:
                lines = f.readlines()
            tail = "".join(lines[-n:]).strip()
            if len(tail) > 3800:
                tail = "…\n" + tail[-3800:]
            await telegram._send(f"<pre>{tail}</pre>")
        except Exception as e:
            await telegram._send(f"❌ Erreur /logs : {e}")

    elif command == "/pause":
        _paused = True
        logger.info("Bot mis en PAUSE via commande Telegram")
        await telegram._send(
            "⏸ <b>Bot en pause</b>\n"
            "Les cycles d'analyse continuent mais aucun nouvel ordre ne sera placé.\n"
            "👉 /resume pour reprendre."
        )

    elif command == "/resume":
        _paused = False
        logger.info("Bot REPRIS via commande Telegram")
        await telegram._send("▶️ <b>Bot actif</b> — signaux et ordres réactivés.")

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
            pnl_str   = f"{'+'if total_pnl > 0 else ''}{total_pnl:.2f} $"

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
                emoji     = "✅" if t["pnl"] >= 0 else "❌"
                d_str     = "LONG " if t["direction"] == "BUY" else "SHORT"
                pnl_s     = f"{'+'if t['pnl'] > 0 else ''}{t['pnl']:.2f} $"
                date_s    = t["closed_at"][8:10] + "/" + t["closed_at"][5:7] + " " + t["closed_at"][11:16]
                name      = t.get("asset_name") or t["symbol"]
                number    = t.get("trade_no") or t["id"]
                lines.append(f"#{number} {emoji} {d_str} {name} | {pnl_s} | {date_s}")

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

    else:
        await telegram._send(
            f"❓ Commande inconnue : <code>{command}</code>\n"
            "👉 /help pour la liste."
        )


def _is_stock_market_open() -> bool:
    """Return True if US regular market hours are active (Mon-Fri, 13:30–20:00 UTC)."""
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open  = now.replace(hour=13, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=20, minute=0,  second=0, microsecond=0)
    return market_open <= now < market_close


def seconds_until_next_m30() -> float:
    """Return seconds until the next M30 candle closes, plus a 5s safety buffer."""
    now       = datetime.now(timezone.utc)
    remaining = ((30 - now.minute % 30) * 60) - now.second
    return max(float(remaining + 5), 5.0)


async def run_cycle(broker: AlpacaBroker, telegram: TelegramNotifier) -> int:
    """Run one analysis cycle. Returns number of signals fired."""
    global _prev_positions, _last_cycle_iso

    now = datetime.now(timezone.utc)
    logger.info("═══ Cycle %s ═══", now.strftime("%Y-%m-%d %H:%M UTC"))

    # Fetch balance — used for connectivity check and dynamic risk sizing
    account_info = await broker.get_account_info()
    balance      = account_info["balance"]
    buying_power = account_info["buying_power"]
    if not balance:
        logger.warning("Balance unavailable — cycle cancelled")
        return 0

    risk_amount = round(balance * RISK_PCT, 2)
    logger.info("Balance: $%.2f | Buying power: $%.2f | Risk per trade: $%.2f (%.1f%%)",
                balance, buying_power, risk_amount, RISK_PCT * 100)

    open_positions = await broker.get_open_positions()
    open_epics     = {p["epic"] for p in open_positions}

    # ── TP/SL monitoring (tous actifs) ───────────────────────────
    # Alpaca simple orders n'ont pas de SL/TP attachés.
    # Le bot les surveille ici à chaque cycle pour tous les actifs.
    for pos in open_positions:
        epic      = pos["epic"]
        deal_id   = pos["deal_id"]
        cache_key = deal_id if BROKER == "ig" else epic
        cache     = _signal_cache.get(cache_key)
        if not cache:
            continue
        current_price = pos.get("current_price", 0.0)
        if current_price <= 0:
            continue

        tp_price  = cache.get("tp", 0.0)
        sl_price  = cache.get("sl", 0.0)
        direction = cache.get("direction", "BUY")

        if direction == "BUY":
            hit_tp = tp_price > 0 and current_price >= tp_price
            hit_sl = sl_price > 0 and current_price <= sl_price
        else:  # SELL / short
            hit_tp = tp_price > 0 and current_price <= tp_price
            hit_sl = sl_price > 0 and current_price >= sl_price

        if hit_tp or hit_sl:
            reason = (
                f"TP={tp_price:,.2f} atteint (prix={current_price:,.2f})" if hit_tp
                else f"SL={sl_price:,.2f} atteint (prix={current_price:,.2f})"
            )
            logger.info("TP/SL triggered — %s | %s | liquidation en cours", epic, reason)
            try:
                if BROKER == "ig":
                    await broker.close_position(epic, deal_id=deal_id)
                else:
                    await broker.close_position(epic)
                # Journal + Telegram close notification handled next cycle
                # via _prev_positions detection + get_closed_orders_since()
                await telegram._send(
                    f"📊 <b>{epic}</b> — fermeture bot-managed\n{reason}"
                )
            except BrokerError as e:
                logger.error("Erreur fermeture TP/SL %s: %s", epic, e)
                await telegram.send_error(f"Close {epic}", str(e))

    # ── Time stop (mean reversion) : clôture après MR_TIME_STOP barres ─
    if BROKER == "ig":
        for pos in open_positions:
            epic    = pos["epic"]
            deal_id = pos["deal_id"]
            cache   = _signal_cache.get(deal_id)
            opened_iso = (cache or {}).get("opened_at") or pos.get("created_at")
            if not opened_iso:
                continue
            try:
                opened_dt = datetime.fromisoformat(opened_iso.replace("Z", "+00:00"))
                if opened_dt.tzinfo is None:
                    opened_dt = opened_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            bars_held = (now - opened_dt).total_seconds() / 1800.0
            if bars_held >= MR_TIME_STOP:
                logger.info("Time stop — %s ouvert depuis %.1f barres (max %d), clôture",
                            epic, bars_held, MR_TIME_STOP)
                try:
                    await broker.close_position(epic, deal_id=deal_id)
                    await telegram._send(
                        f"⏱ <b>{epic}</b> — time stop ({MR_TIME_STOP} barres), "
                        f"clôture au marché"
                    )
                except BrokerError as e:
                    logger.error("Erreur time stop %s: %s", epic, e)
                    await telegram.send_error(f"Time stop {epic}", str(e))

    # ── Detect closed positions ───────────────────────────────────
    if BROKER == "ig":
        # IG : plusieurs positions possibles par epic (scaling), appariement par deal_id.
        current_deal_ids = {p["deal_id"] for p in open_positions}
        missing = [
            (deal_id, pos_data) for deal_id, pos_data in _prev_positions.items()
            if deal_id not in current_deal_ids
        ]
        unmatched_deal_ids: list = []   # (deal_id, epic) — match() a échoué ce cycle

        if missing and _last_cycle_iso:
            epics_to_check = {pos_data["epic"] for _, pos_data in missing}
            closed_by_epic = {
                epic: await broker.get_closed_orders_since(epic, _last_cycle_iso)
                for epic in epics_to_check
            }

            # Tier 1 en premier : son TP est le plus facile à distinguer sans ambiguïté.
            missing.sort(key=lambda item: _signal_cache.get(item[0], {}).get("tier", 99))

            for deal_id, pos_data in missing:
                epic         = pos_data["epic"]
                cache_entry  = _signal_cache.get(deal_id, {})
                candidates   = closed_by_epic.get(epic, [])
                match        = _match_closed_deal(pos_data["direction"], cache_entry, candidates)

                if match is None:
                    logger.warning(
                        "Impossible d'apparier la clôture de %s (deal_id=%s) — ignoré ce cycle",
                        epic, deal_id,
                    )
                    unmatched_deal_ids.append((deal_id, epic))
                    continue
                candidates.remove(match)   # ne pas réutiliser la même transaction

                try:
                    exit_price  = match["filled_avg_price"]
                    entry_price = pos_data["entry_price"]
                    qty         = pos_data["qty"]
                    if match.get("pnl") is not None:
                        pnl = match["pnl"]
                    elif pos_data["direction"] == "BUY":
                        pnl = (exit_price - entry_price) * qty
                    else:
                        pnl = (entry_price - exit_price) * qty

                    tier     = cache_entry.get("tier", 0)
                    trade_no = cache_entry.get("trade_no")
                    logger.info(
                        "Trade closed — #%s %s %s (tier %s) | entry=%.2f exit=%.2f P&L=%.2f",
                        trade_no, pos_data["direction"], epic, tier, entry_price, exit_price, pnl,
                    )
                    await telegram.send_trade_closed(
                        cache_entry.get("asset_name", epic), pos_data["direction"], pnl,
                        DEMO_MODE, tier=tier, trade_no=trade_no,
                        entry=entry_price, exit_price=exit_price,
                        sl=cache_entry.get("sl"), tp=cache_entry.get("tp"), qty=qty,
                    )

                    _add_to_journal(
                        _journal,
                        symbol      = epic,
                        asset_name  = cache_entry.get("asset_name", epic),
                        direction   = pos_data["direction"],
                        entry_price = entry_price,
                        exit_price  = exit_price,
                        sl_price    = cache_entry.get("sl", 0.0),
                        tp_price    = cache_entry.get("tp", 0.0),
                        qty         = qty,
                        pnl         = pnl,
                        closed_at   = now.isoformat(),
                        tier        = tier,
                        trade_no    = trade_no,
                    )
                    _save_journal(_journal)

                    # ── Bascule breakeven : tier 1 fermé en profit ──
                    if pnl > 0 and tier == 1:
                        await _apply_breakeven(broker, telegram, epic, deal_id, cache_entry, current_deal_ids)

                    _signal_cache.pop(deal_id, None)
                    _save_state({"open_signal_cache": _signal_cache})
                except Exception as e:
                    logger.warning("Could not process closed trade for %s (deal_id=%s): %s", epic, deal_id, e)

        # ── Nettoyage des clôtures non appariées ────────────────────
        # _prev_positions est reconstruit ci-dessous à partir de open_positions,
        # qui ne contient plus ces deal_id. Contrairement à l'ancien cache
        # keyé par epic (auto-écrasé par le prochain trade sur le même epic),
        # une entrée keyée par deal_id ne sera plus jamais réécrite : elle
        # fuirait indéfiniment dans _signal_cache/bot_state.json et deviendrait
        # un faux "sibling" testé par _apply_breakeven à chaque clôture future
        # sur cet epic (voir revue finale #4).
        if unmatched_deal_ids:
            removed_any = False
            for deal_id, epic in unmatched_deal_ids:
                if deal_id in _signal_cache:
                    logger.warning(
                        "Clôture non appariée abandonnée — %s (deal_id=%s) retiré du cache sans être journalisé",
                        epic, deal_id,
                    )
                    _signal_cache.pop(deal_id, None)
                    removed_any = True
            if removed_any:
                _save_state({"open_signal_cache": _signal_cache})

        # ── Positions IG inconnues du bot (confirmation perdue) ─────
        adopted = _adopt_unknown_positions(open_positions)
        for entry in adopted:
            logger.warning(
                "Position inconnue adoptée — #%s %s %s entry=%.2f SL=%.2f TP=%.2f qty=%s",
                entry["trade_no"], entry["direction"], entry["asset_name"],
                entry["entry"], entry["sl"], entry["tp"], entry["qty"],
            )
            await telegram._send(
                f"⚠️ <b>Trade #{entry['trade_no']} {entry['asset_name']}</b> retrouvé chez IG "
                f"(confirmation d'ouverture manquée)\n"
                f"Direction : {'LONG' if entry['direction'] == 'BUY' else 'SHORT'}\n"
                f"Entrée : {entry['entry']:.2f} | SL : {entry['sl']:.2f} | TP : {entry['tp']:.2f}\n"
                f"Lot : {entry['qty']:g}"
            )
        if adopted:
            _save_state({"open_signal_cache": _signal_cache})

        # Update position tracking for next cycle
        _prev_positions = {
            p["deal_id"]: {
                "epic":        p["epic"],
                "direction":   p["direction"],
                "entry_price": p.get("entry_price", 0),
                "qty":         p["size"],
            }
            for p in open_positions
        }

    else:
        # Alpaca (legacy) — une seule position par epic, comportement inchangé.
        current_epics = set(open_epics)
        for symbol, pos_data in list(_prev_positions.items()):
            if symbol not in current_epics and _last_cycle_iso:
                try:
                    closed_orders = await broker.get_closed_orders_since(symbol, _last_cycle_iso)
                    closing_side  = "sell" if pos_data["direction"] == "BUY" else "buy"
                    closing_fill  = next(
                        (o for o in closed_orders if o["side"] == closing_side), None
                    )
                    if closing_fill:
                        exit_price  = closing_fill["filled_avg_price"]
                        entry_price = pos_data["entry_price"]
                        qty         = pos_data["qty"]
                        if closing_fill.get("pnl") is not None:
                            # IG fournit le P&L exact (tient compte de la taille de contrat)
                            pnl = closing_fill["pnl"]
                        elif pos_data["direction"] == "BUY":
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
                except Exception as e:
                    logger.warning("Could not process closed trade for %s: %s", symbol, e)

        # Update position tracking for next cycle
        _prev_positions = {
            p["epic"]: {
                "direction":   p["direction"],
                "entry_price": p.get("entry_price", 0),
                "qty":         p["size"],
            }
            for p in open_positions
        }

    _last_cycle_iso = now.isoformat()

    signals_found = 0

    for asset_name, asset_config in ENABLED_ASSETS.items():
        epic = asset_config["symbol"]

        if epic in open_epics:
            # Cache tenu à jour même position ouverte : sinon la bougie de l'entrée
            # reste figée sur son instantané et la reprise doit combler des heures.
            try:
                await get_fresh_candles(broker, epic)
            except Exception as e:
                logger.warning("%s: cache non rafraîchi (position ouverte) : %s", asset_name, e)
            logger.debug("%s: position already open — skip", asset_name)
            continue

        try:
            candles = await get_fresh_candles(broker, epic)
            if not candles:
                continue

            if BROKER == "ig":
                signal = analyse_meanrev(
                    asset_name   = asset_name,
                    asset_config = asset_config,
                    candles      = candles,
                    risk_amount  = risk_amount,
                    bb_len       = MR_BB_LEN,
                    bb_std       = MR_BB_STD,
                    rsi_len      = MR_RSI_LEN,
                    rsi_lo       = MR_RSI_LO,
                    ema_len      = MR_EMA_LEN,
                    atr_len      = MR_ATR_LEN,
                    tp_atr       = MR_TP_ATR,
                    sl_atr       = MR_SL_ATR,
                    sess_start   = MR_SESS_START,
                    sess_end     = MR_SESS_END,
                    now          = now,
                )
            else:
                signal = analyse_asset(
                    asset_name          = asset_name,
                    asset_config        = asset_config,
                    candles             = candles,
                    prev_long           = _prev_long.get(epic, False),
                    prev_short          = _prev_short.get(epic, False),
                    risk_amount         = risk_amount,
                    donchian_length     = DONCHIAN_LENGTH,
                    global_point_value  = POINT_VALUE,
                    global_rr_ratio     = RR_RATIO,
                )

            if not signal:
                # Pas de signal — réinitialiser les flags anti-doublon
                _prev_long[epic]  = False
                _prev_short[epic] = False
                continue

            # ── Market hours gate (stocks uniquement) ─────────────
            # Alpaca rejette les ordres sur les actifs fractionnables
            # (SPY, QQQ…) en dehors des heures de marché (lun-ven 13:30-20:00 UTC).
            # Si hors horaires : on ne place pas l'ordre ET on ne touche pas aux
            # flags anti-doublon, pour que le signal puisse se rejouer au prochain cycle.
            is_crypto = asset_config.get("crypto", False)
            if BROKER == "alpaca" and not is_crypto and not _is_stock_market_open():
                logger.info(
                    "%s: signal %s hors-marché — ordre reporté à l'ouverture (13:30 UTC)",
                    asset_name, signal["direction"],
                )
                await telegram._send(
                    f"⏰ Signal {signal['direction']} <b>{asset_name}</b> hors-marché\n"
                    f"Ordre reporté à l'ouverture du marché (13:30 UTC)."
                )
                continue

            # Signal actif et marché ouvert — marquer pour anti-doublon
            _prev_long[epic]  = signal["direction"] == "BUY"
            _prev_short[epic] = signal["direction"] == "SELL"

            # ── Plafond de taille (protection buying power) ───────
            # qty = risk/sl_distance peut exploser si le SL est très proche.
            # On plafonne le notionnel à 50 % du solde pour ne jamais
            # dépasser le buying_power disponible (Alpaca = 2× le cash).
            contract_size = float(asset_config.get("contract_size", 1.0))
            max_notional  = buying_power * 0.95
            notional      = signal["qty"] * signal["entry_price"] * contract_size
            if notional > max_notional:
                if BROKER == "ig":
                    capped_qty = round(max_notional / (signal["entry_price"] * contract_size), 1)
                elif is_crypto:
                    capped_qty = round(max_notional / signal["entry_price"], 6)
                else:
                    capped_qty = math.floor(max_notional / signal["entry_price"])
                if capped_qty <= 0:
                    logger.warning(
                        "%s: qty après plafonnement = 0 — signal ignoré", asset_name
                    )
                    continue
                logger.info(
                    "%s: qty plafonnée %.4f → %.4f "
                    "(notionnel $%.0f > max $%.0f = 95%% buying_power)",
                    asset_name, signal["qty"], capped_qty, notional, max_notional,
                )
                signal = {**signal, "qty": capped_qty}

            # ── Cooldown après echec recent d'ordre sur cet epic ──
            last_failure = _order_failure_cooldown.get(epic)
            if last_failure:
                elapsed_min = (now - datetime.fromisoformat(last_failure)).total_seconds() / 60.0
                if elapsed_min < _ORDER_FAILURE_COOLDOWN_MINUTES:
                    logger.info(
                        "%s: signal %s détecté — en cooldown après échec (%.0f/%d min), ordre non retenté",
                        asset_name, signal["direction"], elapsed_min, _ORDER_FAILURE_COOLDOWN_MINUTES,
                    )
                    continue
                del _order_failure_cooldown[epic]

            # Pause active → log le signal mais ne place pas d'ordre
            if _paused:
                logger.info(
                    "%s: signal %s détecté — BOT EN PAUSE, ordre non envoyé",
                    asset_name, signal["direction"]
                )
                await telegram._send(
                    f"⏸ Signal {signal['direction']} <b>{asset_name}</b> détecté\n"
                    f"Bot en pause — ordre non placé."
                )
                continue

            # Place the order(s)
            if BROKER == "ig":
                orders = build_scaled_orders(
                    signal, risk_amount, contract_size,
                    # Position unique (retour arriere du scaling 3 paliers, 2026-09-19) :
                    # backtest sur signaux reels/Dukascopy montre qu'un seul palier a
                    # TP 1.0xATR bat le meilleur reglage de paliers trouve (voir
                    # commentaire config.py::MR_TP_ATR). build_scaled_orders() avec un
                    # seul multiplicateur cree un ordre unique, qty = risk_amount total.
                    tp_atr_multipliers=(MR_TP_ATR,),
                )
                # build_scaled_orders() re-dérive qty à partir de risk_amount/sl_dist et
                # ignore donc le plafonnement buying-power appliqué plus haut sur
                # signal["qty"]. Sans ce clamp, un SL très serré peut produire des ordres
                # dépassant largement le plafond de marge voulu (voir revue finale #1).
                if orders:
                    capped_per_tier = max(round(signal["qty"] / len(orders), 1), 0.1)
                    for order in orders:
                        order["qty"] = min(order["qty"], capped_per_tier)
                any_failed = False
                for order in orders:
                    try:
                        if order["direction"] == "BUY":
                            deal_id = await broker.open_long(
                                epic, order["qty"], order["sl_price"], order["tp_price"],
                                comment=f"ZorionBot_{asset_name}_T{order['tier']}",
                                currency_code=asset_config.get("currency_code", "EUR"),
                            )
                        else:
                            deal_id = await broker.open_short(
                                epic, order["qty"], order["sl_price"], order["tp_price"],
                                comment=f"ZorionBot_{asset_name}_T{order['tier']}",
                                currency_code=asset_config.get("currency_code", "EUR"),
                            )
                        if not deal_id:
                            raise BrokerError(
                                f"Aucun deal_id retourné pour le palier {order['tier']}"
                            )

                        signals_found += 1
                        trade_no = _allocate_trade_no()
                        # Prix réellement exécuté par IG (le signal part de la clôture de
                        # bougie) : c'est lui que le journal retient déjà via /positions.
                        fill = getattr(broker, "last_fill_level", None) or order["entry_price"]
                        if fill != order["entry_price"]:
                            logger.info("Trade #%s : signal %.2f → exécuté %.2f (écart %+.2f)",
                                        trade_no, order["entry_price"], fill,
                                        fill - order["entry_price"])
                        order = {**order, "entry_price": fill}
                        _signal_cache[deal_id] = {
                            "trade_no":   trade_no,
                            "epic":       epic,
                            "asset_name": asset_name,
                            "direction":  order["direction"],
                            "tier":       order["tier"],
                            "entry":      order["entry_price"],
                            "sl":         order["sl_price"],
                            "tp":         order["tp_price"],
                            "atr":        signal["atr"],
                            "qty":        order["qty"],
                            "opened_at":  now.isoformat(),
                        }
                        _prev_positions[deal_id] = {
                            "epic":        epic,
                            "direction":   order["direction"],
                            "entry_price": order["entry_price"],
                            "qty":         order["qty"],
                        }
                        await telegram.send_signal(
                            order, DEMO_MODE, trade_no=trade_no,
                            point_value=asset_config.get("point_value", 1.0),
                        )

                    except BrokerError as e:
                        any_failed = True
                        logger.error("BrokerError %s tier %d: %s", asset_name, order["tier"], e)
                        await telegram.send_error(f"Order {asset_name} tier {order['tier']}", str(e))

                if orders:
                    _save_state({"open_signal_cache": _signal_cache})
                if any_failed:
                    _order_failure_cooldown[epic] = now.isoformat()

            else:
                # Chemin Alpaca (legacy) — comportement inchangé, une seule position.
                try:
                    if signal["direction"] == "BUY":
                        await broker.open_long(
                            epic, signal["qty"], signal["sl_price"], signal["tp_price"],
                            comment=f"ZorionBot_{asset_name}",
                            currency_code=asset_config.get("currency_code", "EUR"),
                        )
                    else:
                        await broker.open_short(
                            epic, signal["qty"], signal["sl_price"], signal["tp_price"],
                            comment=f"ZorionBot_{asset_name}",
                            currency_code=asset_config.get("currency_code", "EUR"),
                        )
                    signals_found += 1
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
                    _prev_positions[epic] = {
                        "direction":   signal["direction"],
                        "entry_price": signal["entry_price"],
                        "qty":         signal["qty"],
                    }
                    await telegram.send_signal(signal, DEMO_MODE)

                except BrokerError as e:
                    logger.error("BrokerError %s: %s", asset_name, e)
                    _order_failure_cooldown[epic] = now.isoformat()
                    await telegram.send_error(
                        f"Order {asset_name}",
                        f"{e}\n⏸ Pas de nouvelle tentative pendant {_ORDER_FAILURE_COOLDOWN_MINUTES} min.",
                    )

        except Exception as e:
            logger.error("Error %s: %s", asset_name, e, exc_info=True)
            await telegram.send_error(f"Analysis {asset_name}", str(e))

        await asyncio.sleep(1)   # polite rate limiting between assets

    logger.info(
        "Cycle done — signals: %d | open positions: %d",
        signals_found, len(open_positions)
    )
    return signals_found


async def main() -> None:
    logger.info("╔══════════════════════════════╗")
    logger.info("║   ZorionBot started          ║")
    logger.info("║  Mode : %-6s               ║", "DEMO" if DEMO_MODE else "LIVE")
    logger.info("╚══════════════════════════════╝")

    if BROKER == "ig":
        if not (IG_API_KEY and IG_IDENTIFIER and IG_PASSWORD):
            logger.critical("IG_API_KEY / IG_IDENTIFIER / IG_PASSWORD manquants dans .env — stop.")
            return
        broker = IGBroker(IG_API_KEY, IG_IDENTIFIER, IG_PASSWORD, DEMO_MODE)
        logger.info("Broker : IG Markets | Stratégie : Mean Reversion XAUUSD v5 | Risque : %.1f%%",
                    RISK_PCT * 100)
    else:
        if not ALPACA_API_KEY:
            logger.critical("ALPACA_API_KEY not configured in .env — stopping.")
            return
        broker = AlpacaBroker(ALPACA_API_KEY, ALPACA_API_SECRET, DEMO_MODE)
    telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID)

    await telegram.send_test_message()

    # Connect with retry (max 3 attempts, 60s between)
    connected = False
    for attempt in range(1, 4):
        try:
            await broker.connect()
            connected = True
            break
        except BrokerError as e:
            logger.error("Attempt %d/3 — Alpaca connection failed: %s", attempt, e)
            await telegram.send_error("Startup", f"Attempt {attempt}/3 — {e}")
            if attempt == 3:
                logger.critical("Cannot connect to Alpaca — stopping.")
            else:
                await asyncio.sleep(60)

    if not connected:
        await broker.disconnect()
        return

    await telegram.send_startup(DEMO_MODE, list(ENABLED_ASSETS.keys()))
    _load_disk_cache()

    bot_state    = _load_state()
    last_summary = bot_state.get("last_summary")

    global _journal, _signal_cache
    _journal = _load_journal()
    _signal_cache = bot_state.get("open_signal_cache", {})
    logger.info(
        "Journal chargé — %s : %d trade(s) | Signal cache : %d entrée(s)",
        _journal["month"], len(_journal["trades"]), len(_signal_cache),
    )
    trades_today = 0
    logger.info("Bot state loaded — last_summary: %s", last_summary)

    # ── Tâche de fond : écoute des commandes Telegram ─────────────
    async def _command_listener():
        await telegram.poll_commands(
            lambda cmd, args: handle_telegram_command(cmd, args, broker, telegram)
        )

    command_task = asyncio.create_task(_command_listener())
    logger.info("Écoute des commandes Telegram démarrée")

    try:
        while True:
            try:
                wait = seconds_until_next_m30()
                logger.info("Next scan in %.0fs", wait)
                await asyncio.sleep(wait)

                now       = datetime.now(timezone.utc)
                today_str = now.strftime("%Y-%m-%d")

                # Daily summary at 08:00 UTC
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

                signals = await run_cycle(broker, telegram)
                trades_today += signals

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Main loop error: %s", e, exc_info=True)
                await telegram.send_error("Main loop", str(e))
                await asyncio.sleep(60)

    finally:
        command_task.cancel()
        try:
            await command_task
        except asyncio.CancelledError:
            pass
        await broker.disconnect()
        await telegram.close()
        logger.info("ZorionBot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Manual stop.")
