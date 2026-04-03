"""
strategy.py — LONG/SHORT signal logic for Donchian V1.1 (Heiken Ashi).

Faithful translation of the Pine Script strategy.
Candle indexing: candles[-1] = signal candle (last closed), candles[-2] = previous.
Signal conditions use Heiken Ashi values; entry/SL use raw prices.

LONG conditions (all must be true):
  - any(hl <= lower for hl in ha_lows[-3:])   — HA touched LOWER band in last 3 candles
  - ha_closes[-1] > ha_opens[-1]               — HA signal candle is bullish
  - ha_closes[-1] > ha_highs[-2]               — HA close breaks previous HA high
  - ha_opens[-1] < limitLow                    — HA open is in buy zone
  - zlmacd < 0                                 — bearish context (mean reversion filter)
  - not prev_long                              — anti-doublon

SHORT conditions (symmetric):
  - any(hh >= upper for hh in ha_highs[-3:])  — HA touched UPPER band in last 3 candles
  - ha_closes[-1] < ha_opens[-1]               — HA signal candle is bearish
  - ha_closes[-1] < ha_lows[-2]                — HA close breaks previous HA low
  - ha_opens[-1] > limitHigh                   — HA open is in sell zone
  - zlmacd > 0                                 — bullish context (mean reversion filter)
  - not prev_short                             — anti-doublon
"""
import logging
from typing import Optional, List, Dict

from indicators import donchian_channel, zlmacd, heiken_ashi
import risk as risk_module

logger = logging.getLogger(__name__)


def analyse_asset(
    asset_name:          str,
    asset_config:        Dict,
    candles:             List[Dict],
    prev_long:           bool,
    prev_short:          bool,
    risk_amount:         float,
    donchian_length:     int,
    global_point_value:  float = 1.0,
    global_rr_ratio:     float = 2.0,
) -> Optional[Dict]:
    """
    Analyse candles and return a signal dict or None.

    Args:
        asset_name:         Human-readable asset name (e.g. "DAX")
        asset_config:       Dict with symbol, point_value, rr_ratio
        candles:            List of candle dicts (needs at least donchian_length + 60)
        prev_long:          True if a LONG signal fired on the previous candle
        prev_short:         True if a SHORT signal fired on the previous candle
        risk_amount:        Amount to risk per trade
        donchian_length:    Donchian channel period
        global_point_value: Fallback point_value from .env (used if not set per asset)
        global_rr_ratio:    Fallback rr_ratio from .env (used if not set per asset)

    Returns:
        Signal dict or None.
        Signal keys: direction, entry_price, sl_price, tp_price, qty, asset_name, symbol
    """
    min_candles = donchian_length + 60
    if len(candles) < min_candles:
        logger.debug(
            "%s: not enough candles (%d < %d)", asset_name, len(candles), min_candles
        )
        return None

    opens  = [c["open"]  for c in candles]
    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]
    closes = [c["close"] for c in candles]

    # ── Indicators ────────────────────────────────────────────────
    upper, lower, _, limitHigh, limitLow = donchian_channel(highs, lows, donchian_length)

    try:
        macd_value = zlmacd(closes)
    except ValueError as e:
        logger.debug("%s: zlmacd unavailable — %s", asset_name, e)
        return None

    ha_opens, ha_highs, ha_lows, ha_closes = heiken_ashi(opens, highs, lows, closes)

    # ── Common conditions (HA-based) ──────────────────────────────
    touched_upper = any(hh >= upper for hh in ha_highs[-3:])
    touched_lower = any(hl <= lower for hl in ha_lows[-3:])

    # ── LONG signal ───────────────────────────────────────────────
    raw_long = (
        touched_lower                              # HA touched LOWER band
        and ha_closes[-1] > ha_opens[-1]           # bullish HA candle
        and ha_closes[-1] > ha_highs[-2]           # HA close breaks previous HA high
        and ha_opens[-1]  < limitLow               # HA open in buy zone
        and macd_value < 0                         # ZL-MACD filter
    )
    long_signal = raw_long and not prev_long

    # ── SHORT signal ──────────────────────────────────────────────
    raw_short = (
        touched_upper                              # HA touched UPPER band
        and ha_closes[-1] < ha_opens[-1]           # bearish HA candle
        and ha_closes[-1] < ha_lows[-2]            # HA close breaks previous HA low
        and ha_opens[-1]  > limitHigh              # HA open in sell zone
        and macd_value > 0                         # ZL-MACD filter
    )
    short_signal = raw_short and not prev_short

    if not long_signal and not short_signal:
        return None

    # ── Price levels ──────────────────────────────────────────────
    # Per-asset value takes priority; fall back to global .env value
    point_value = asset_config.get("point_value") or global_point_value
    rr_ratio    = asset_config.get("rr_ratio")    or global_rr_ratio

    if long_signal:
        direction   = "BUY"
        entry_price = highs[-2]
        sl_price    = min(lows[-1], lows[-2])
    else:
        direction   = "SELL"
        entry_price = lows[-2]
        sl_price    = max(highs[-1], highs[-2])

    qty      = risk_module.calculate_size(risk_amount, entry_price, sl_price, point_value)
    tp_price = risk_module.calculate_tp(entry_price, sl_price, rr_ratio, direction)

    if qty <= 0:
        logger.warning("%s: zero qty (entry == sl), signal skipped", asset_name)
        return None

    return {
        "direction":   direction,
        "entry_price": entry_price,
        "sl_price":    sl_price,
        "tp_price":    tp_price,
        "qty":         qty,
        "asset_name":  asset_name,
        "symbol":      asset_config["symbol"],
    }
