"""
strategy.py — LONG/SHORT signal logic for Donchian V1.1.

Faithful translation of the Pine Script strategy.
Candle indexing: candles[-1] = signal candle (last closed), candles[-2] = previous.

LONG conditions (all must be true):
  - any(l <= lower for l in lows[-3:])   — price touched LOWER band in last 3 candles
  - closes[-1] > opens[-1]               — signal candle is bullish
  - closes[-1] > highs[-2]               — close breaks previous candle's high
  - opens[-1] < limitLow                 — open is in buy zone
  - zlmacd < 0                           — bearish context (mean reversion filter)
  - not prev_long                        — anti-doublon

SHORT conditions (symmetric):
  - any(h >= upper for h in highs[-3:])  — price touched UPPER band in last 3 candles
  - closes[-1] < opens[-1]               — signal candle is bearish
  - closes[-1] < lows[-2]               — close breaks previous candle's low
  - opens[-1] > limitHigh               — open is in sell zone
  - zlmacd > 0                           — bullish context (mean reversion filter)
  - not prev_short                       — anti-doublon
"""
import logging
from typing import Optional, List, Dict

from indicators import donchian_channel, zlmacd
import risk as risk_module

logger = logging.getLogger(__name__)


def analyse_asset(
    asset_name:      str,
    asset_config:    Dict,
    candles:         List[Dict],
    prev_long:       bool,
    prev_short:      bool,
    risk_amount:     float,
    donchian_length: int,
) -> Optional[Dict]:
    """
    Analyse candles and return a signal dict or None.

    Args:
        asset_name:      Human-readable asset name (e.g. "DAX")
        asset_config:    Dict with symbol, point_value, rr_ratio
        candles:         List of candle dicts (needs at least donchian_length + 60)
        prev_long:       True if a LONG signal fired on the previous candle
        prev_short:      True if a SHORT signal fired on the previous candle
        risk_amount:     Amount to risk per trade
        donchian_length: Donchian channel period

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

    # ── Common conditions ─────────────────────────────────────────
    touched_upper = any(h >= upper for h in highs[-3:])
    touched_lower = any(l <= lower for l in lows[-3:])

    # ── LONG signal ───────────────────────────────────────────────
    raw_long = (
        touched_lower                      # price touched LOWER band
        and closes[-1] > opens[-1]         # bullish signal candle
        and closes[-1] > highs[-2]         # close breaks previous high
        and opens[-1]  < limitLow          # open in buy zone
        and macd_value < 0                 # ZL-MACD filter
    )
    long_signal = raw_long and not prev_long

    # ── SHORT signal ──────────────────────────────────────────────
    raw_short = (
        touched_upper                      # price touched UPPER band
        and closes[-1] < opens[-1]         # bearish signal candle
        and closes[-1] < lows[-2]          # close breaks previous low
        and opens[-1]  > limitHigh         # open in sell zone
        and macd_value > 0                 # ZL-MACD filter
    )
    short_signal = raw_short and not prev_short

    if not long_signal and not short_signal:
        return None

    # ── Price levels ──────────────────────────────────────────────
    point_value = asset_config.get("point_value", 1.0)
    rr_ratio    = asset_config.get("rr_ratio", 2.0)

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
