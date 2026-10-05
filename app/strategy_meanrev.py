"""
strategy_meanrev.py — Mean Reversion XAUUSD v5 (portage du Pine Script validé).

Backtest de référence (Dukascopy M30, 2025-01 -> 2026-07, spread 0.5 $/oz) :
263 trades, 88.6% WR, +1635 $, PF 1.35 — profitable sur 2025 ET 2026 séparément.

Signal évalué sur la dernière bougie CLÔTURÉE. Le cache IG contient aussi la bougie
en cours (ouverte depuis quelques secondes au moment du cycle) : elle est écartée.
Si la dernière bougie clôturée date de plus d'une barre (marché fermé le week-end,
cache non rafraîchi), aucun signal : on ne trade pas un signal périmé.
  LONG  : close < BB inférieure (20, 1.5) ET RSI(14) < 40 ET close > EMA200
  SHORT : close > BB supérieure          ET RSI(14) > 60 ET close < EMA200
  Session : heure UTC de la bougie signal dans [5h, 22h), jours ouvrés uniquement.

Sorties (gérées par IG via SL/TP attachés + time stop dans main.py) :
  TP = entrée ± 0.5 × ATR(14)   |   SL = entrée ∓ 5 × ATR(14)   |   time stop 16 barres (8h)

Sizing : risque fixe en % de l'équity. qty (contrats) = risk_amount / (dist_SL × contract_size),
arrondi au pas de 0.1 contrat (mini or = 10 oz/contrat, 0.1 = 1 oz).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from indicators import atr, bollinger, ema, rsi

logger = logging.getLogger(__name__)

MIN_CANDLES = 215   # EMA200 + marge
BAR         = timedelta(minutes=30)


def _candle_start_utc(time_str: str) -> datetime:
    """Heure d'ouverture UTC de la bougie. IG : 'YYYY-MM-DDTHH:MM:SS' en UTC."""
    return datetime.fromisoformat(time_str.replace("Z", "")).replace(tzinfo=timezone.utc)


def analyse_meanrev(
    asset_name:    str,
    asset_config:  Dict,
    candles:       List[Dict],
    risk_amount:   float,
    bb_len:        int   = 20,
    bb_std:        float = 1.5,
    rsi_len:       int   = 14,
    rsi_lo:        float = 40.0,
    ema_len:       int   = 200,
    atr_len:       int   = 14,
    tp_atr:        float = 0.5,
    sl_atr:        float = 5.0,
    sess_start:    int   = 5,
    sess_end:      int   = 22,
    now:           Optional[datetime] = None,
) -> Optional[Dict]:
    """Analyse les bougies et retourne un signal dict ou None."""
    now = now or datetime.now(timezone.utc)

    # ── Bougie en cours écartée, bougie périmée refusée ───────────
    if candles and _candle_start_utc(candles[-1]["time"]) + BAR > now:
        candles = candles[:-1]
    if not candles:
        return None
    last_start = _candle_start_utc(candles[-1]["time"])
    if now - (last_start + BAR) > BAR:
        logger.info("%s: dernière bougie clôturée périmée (%s) — pas de signal",
                    asset_name, candles[-1]["time"])
        return None

    if len(candles) < MIN_CANDLES:
        logger.debug("%s: pas assez de bougies (%d < %d)", asset_name, len(candles), MIN_CANDLES)
        return None

    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]
    closes = [c["close"] for c in candles]
    close  = closes[-1]

    # ── Filtre session + jours ouvrés (heure de la bougie signal) ─
    hour, weekday = last_start.hour, last_start.weekday()
    if weekday >= 5 or not (sess_start <= hour < sess_end):
        return None

    upper, lower, _ = bollinger(closes, bb_len, bb_std)
    rsi_val  = rsi(closes, rsi_len)
    ema_val  = ema(closes, ema_len)
    atr_val  = atr(highs, lows, closes, atr_len)

    long_sig  = close < lower and rsi_val < rsi_lo and close > ema_val
    short_sig = close > upper and rsi_val > 100 - rsi_lo and close < ema_val

    logger.info(
        "%s | close=%.2f BBup=%.2f BBlow=%.2f RSI=%.1f EMA200=%.2f ATR=%.2f | LONG=%s SHORT=%s",
        asset_name, close, upper, lower, rsi_val, ema_val, atr_val, long_sig, short_sig,
    )

    if not long_sig and not short_sig:
        return None

    direction = "BUY" if long_sig else "SELL"
    sign      = 1 if long_sig else -1
    entry     = close                       # approx. : fill au marché à l'open suivant
    sl_price  = entry - sign * sl_atr * atr_val
    tp_price  = entry + sign * tp_atr * atr_val

    contract_size = float(asset_config.get("contract_size", 1.0))
    sl_dist       = abs(entry - sl_price)
    if sl_dist <= 0 or risk_amount <= 0:
        return None
    qty = risk_amount / (sl_dist * contract_size)
    qty = max(round(qty, 1), 0.1)           # pas IG : 0.1 contrat minimum

    return {
        "direction":   direction,
        "entry_price": entry,
        "sl_price":    round(sl_price, 2),
        "tp_price":    round(tp_price, 2),
        "qty":         qty,
        "asset_name":  asset_name,
        "symbol":      asset_config["symbol"],
        "atr":         round(atr_val, 4),
    }
