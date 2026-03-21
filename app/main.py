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

import httpx

from config import (
    IG_API_KEY, IG_IDENTIFIER, IG_PASSWORD, DEMO_MODE,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    RISK_AMOUNT, DONCHIAN_LENGTH, LOOKBACK_CANDLES,
    LOG_FILE, LOG_LEVEL, DATA_DIR,
)
from assets_config import ENABLED_ASSETS
from brokers.ig_broker import IGBroker
from brokers.base_broker import BrokerError
from strategy import analyse_asset
from telegram_notifier import TelegramNotifier

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

# ── Previous signal tracking (anti-doublon) ───────────────────────
_prev_long:  dict = {}   # {epic: bool}
_prev_short: dict = {}   # {epic: bool}


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


async def get_fresh_candles(broker: IGBroker, epic: str) -> list:
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
                logger.warning("IG quota exceeded for %s — asset skipped", epic)
                return []
            raise

    elif epic not in _startup_done:
        # Level 2: catch-up after disk cache load
        try:
            new_candles = await broker.get_candles(epic, 10)
            _startup_done.add(epic)
            if new_candles:
                existing    = _candle_cache[epic]
                known_times = {c["time"] for c in existing}
                added       = [c for c in new_candles if c["time"] not in known_times]
                if added:
                    _candle_cache[epic] = (existing + added)[-LOOKBACK_CANDLES:]
                    _save_disk_cache()
            logger.info("Cache caught up — %s", epic)
        except BrokerError as e:
            if e.status_code == 403:
                logger.warning("Quota exceeded for %s — using disk cache", epic)
                _startup_done.add(epic)
            else:
                raise

    else:
        # Level 3: incremental update each cycle
        try:
            new_candles = await broker.get_candles(epic, 3)
            if new_candles:
                existing    = _candle_cache[epic]
                known_times = {c["time"] for c in existing}
                added       = [c for c in new_candles if c["time"] not in known_times]
                if added:
                    _candle_cache[epic] = (existing + added)[-LOOKBACK_CANDLES:]
                    _save_disk_cache()
        except BrokerError as e:
            if e.status_code == 403:
                logger.warning("Quota exceeded for %s — analysing from cache", epic)
            else:
                raise

    return _candle_cache.get(epic, [])


def seconds_until_next_m30() -> float:
    """Return seconds until the next M30 candle closes, plus a 5s safety buffer."""
    now       = datetime.now(timezone.utc)
    remaining = ((30 - now.minute % 30) * 60) - now.second
    return max(float(remaining + 5), 5.0)


async def run_cycle(broker: IGBroker, telegram: TelegramNotifier) -> int:
    """Run one analysis cycle. Returns number of signals fired."""
    now = datetime.now(timezone.utc)
    logger.info("═══ Cycle %s ═══", now.strftime("%Y-%m-%d %H:%M UTC"))

    balance = await broker.get_account_balance()
    if not balance:
        logger.warning("Balance unavailable — cycle cancelled")
        return 0

    open_positions = await broker.get_open_positions()
    open_epics     = {p["epic"] for p in open_positions}

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
                asset_name      = asset_name,
                asset_config    = asset_config,
                candles         = candles,
                prev_long       = _prev_long.get(epic, False),
                prev_short      = _prev_short.get(epic, False),
                risk_amount     = RISK_AMOUNT,
                donchian_length = DONCHIAN_LENGTH,
            )

            # Update previous signal state for anti-doublon
            _prev_long[epic]  = signal is not None and signal["direction"] == "BUY"
            _prev_short[epic] = signal is not None and signal["direction"] == "SELL"

            if not signal:
                continue

            signals_found += 1

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

    if not IG_API_KEY or "VOTRE" in IG_API_KEY:
        logger.critical("IG_API_KEY not configured in .env — stopping.")
        return

    broker   = IGBroker(IG_API_KEY, IG_IDENTIFIER, IG_PASSWORD, DEMO_MODE)
    telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    await telegram.send_test_message()

    # Connect with retry (max 3 attempts, 60s between)
    for attempt in range(1, 4):
        try:
            await broker.connect()
            break
        except BrokerError as e:
            logger.error("Attempt %d/3 — IG connection failed: %s", attempt, e)
            await telegram.send_error("Startup", f"Attempt {attempt}/3 — {e}")
            if attempt == 3:
                logger.critical("Cannot connect to IG — stopping.")
                return
            await asyncio.sleep(60)

    await telegram.send_startup(DEMO_MODE, list(ENABLED_ASSETS.keys()))
    _load_disk_cache()

    last_summary = None
    trades_today = 0

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
                    positions = await broker.get_open_positions()
                    await telegram.send_daily_summary(trades_today, positions)
                    last_summary = today_str
                    trades_today = 0

                signals = await run_cycle(broker, telegram)
                trades_today += signals

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Main loop error: %s", e, exc_info=True)
                await telegram.send_error("Main loop", str(e))
                await asyncio.sleep(60)

    finally:
        await broker.disconnect()
        logger.info("DonchianBot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Manual stop.")
