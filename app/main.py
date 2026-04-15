#!/usr/bin/env python3
"""
main.py — DonchianBot main loop
Strategy : Donchian Channel V1.1 (LONG + SHORT)
Timeframe: M30
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from config import (
    ALPACA_API_KEY, ALPACA_API_SECRET, DEMO_MODE,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    RISK_PCT, DONCHIAN_LENGTH, LOOKBACK_CANDLES,
    POINT_VALUE, RR_RATIO,
    LOG_FILE, LOG_LEVEL, DATA_DIR,
)
from assets_config import ENABLED_ASSETS
from brokers.alpaca_broker import AlpacaBroker
from brokers.base_broker import BrokerError
from strategy import analyse_asset
from telegram_notifier import TelegramNotifier, _format_open_position

# ── Logging ───────────────────────────────────────────────────────
os.makedirs(DATA_DIR, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("DonchianBot")

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
_signal_cache: dict = {}     # {symbol: {sl, tp, qty, entry, asset_name, direction, opened_at}}


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

# ── Previous signal tracking (anti-doublon) ───────────────────────
_prev_long:  dict = {}   # {epic: bool}
_prev_short: dict = {}   # {epic: bool}

# ── Position tracking (closed trade detection) ────────────────────
_prev_positions: dict = {}   # {symbol: {direction, entry_price, qty}}
_last_cycle_iso: str  = ""   # ISO timestamp of last cycle (for order lookup)

# ── Pause / commandes Telegram ────────────────────────────────────
_paused: bool = False         # True = cycles tournent mais ordres bloqués


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
            last_start = existing[-1]["time"] if existing else ""
            new_candles = await broker.get_candles(epic, 1000, start=last_start)
            _startup_done.add(epic)
            if new_candles:
                known_times = {c["time"] for c in existing}
                added       = [c for c in new_candles if c["time"] not in known_times]
                if added:
                    _candle_cache[epic] = (existing + added)[-LOOKBACK_CANDLES:]
                    _save_disk_cache()
                    logger.info("Cache caught up — %s: +%d candle(s)", epic, len(added))
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
            last_start = existing[-1]["time"] if existing else ""
            new_candles = await broker.get_candles(epic, 3, start=last_start)
            if new_candles:
                known_times = {c["time"] for c in existing}
                added       = [c for c in new_candles if c["time"] not in known_times]
                if added:
                    _candle_cache[epic] = (existing + added)[-LOOKBACK_CANDLES:]
                    _save_disk_cache()
                    logger.info("Cache updated — %s: +%d candle(s)", epic, len(added))
        except BrokerError as e:
            if e.status_code == 403:
                logger.warning("Quota exceeded for %s — analysing from cache", epic)
            else:
                raise

    return _candle_cache.get(epic, [])


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
            "🤖 <b>DonchianBot — Commandes</b>\n\n"
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
                f"🤖 <b>{mode_tag}DonchianBot</b>",
                f"⏰ {now_str}",
                f"💰 Balance   : ${balance:,.2f}",
                f"🎯 Risk/trade : ${risk_amt:.2f} ({RISK_PCT * 100:.1f}%)",
                f"⏸ Pause     : {'OUI ⚠️' if _paused else 'non'}",
            ]
            if positions:
                lines.append(f"\n📈 <b>Positions ({len(positions)}) :</b>")
                for idx, p in enumerate(positions, 1):
                    cache_entry = _signal_cache.get(p["epic"])
                    lines.append(_format_open_position(idx, p, cache_entry))
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
                emoji  = "✅" if t["pnl"] >= 0 else "❌"
                d_str  = "LONG " if t["direction"] == "BUY" else "SHORT"
                pnl_s  = f"{'+'if t['pnl'] > 0 else ''}{t['pnl']:.2f} $"
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

    else:
        await telegram._send(
            f"❓ Commande inconnue : <code>{command}</code>\n"
            "👉 /help pour la liste."
        )


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
    balance = await broker.get_account_balance()
    if not balance:
        logger.warning("Balance unavailable — cycle cancelled")
        return 0

    risk_amount = round(balance * RISK_PCT, 2)
    logger.info("Balance: $%.2f | Risk per trade: $%.2f (%.1f%%)",
                balance, risk_amount, RISK_PCT * 100)

    open_positions = await broker.get_open_positions()
    open_epics     = {p["epic"] for p in open_positions}

    # ── Detect closed positions ───────────────────────────────────
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
            logger.debug("%s: position already open — skip", asset_name)
            continue

        try:
            candles = await get_fresh_candles(broker, epic)
            if not candles:
                continue

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

            # Update previous signal state for anti-doublon
            _prev_long[epic]  = signal is not None and signal["direction"] == "BUY"
            _prev_short[epic] = signal is not None and signal["direction"] == "SELL"

            if not signal:
                continue

            signals_found += 1

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
    logger.info("║   DonchianBot started        ║")
    logger.info("║  Mode : %-6s               ║", "DEMO" if DEMO_MODE else "LIVE")
    logger.info("╚══════════════════════════════╝")

    if not ALPACA_API_KEY:
        logger.critical("ALPACA_API_KEY not configured in .env — stopping.")
        return

    broker = AlpacaBroker(ALPACA_API_KEY, ALPACA_API_SECRET, DEMO_MODE)
    telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

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
        logger.info("DonchianBot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Manual stop.")
