"""Tests de strategy_meanrev (signaux v5) et des nouveaux indicateurs."""
import math

import pytest

from indicators import atr, bollinger, ema, rsi
from strategy_meanrev import MIN_CANDLES, analyse_meanrev

GOLD_CFG = {
    "symbol":        "CS.D.CFEGOLD.CEF.IP",
    "contract_size": 1.0,
    "currency_code": "USD",
}


def make_candles(closes, time_prefix="2026-07-15T", hour=10):
    """Bougies plates (O=H=L=C) horodatées un mercredi à `hour` UTC."""
    candles = []
    for i, c in enumerate(closes):
        candles.append({
            "time":  f"{time_prefix}{hour:02d}:00:00",
            "open":  c, "high": c, "low": c, "close": c,
        })
    return candles


# ── Indicateurs ───────────────────────────────────────────────────

def test_bollinger_flat_series():
    up, lo, basis = bollinger([100.0] * 25, 20, 1.5)
    assert up == lo == basis == 100.0


def test_bollinger_known_values():
    closes = list(range(1, 21))  # 1..20
    up, lo, basis = bollinger([float(c) for c in closes], 20, 2.0)
    assert basis == 10.5
    # stdev population de 1..20 = sqrt(33.25)
    assert math.isclose(up, 10.5 + 2 * math.sqrt(33.25))
    assert math.isclose(lo, 10.5 - 2 * math.sqrt(33.25))


def test_rsi_all_up_is_100():
    closes = [float(i) for i in range(1, 30)]
    assert rsi(closes, 14) == 100.0


def test_rsi_mixed_range():
    closes = [100 + (1 if i % 2 else -1) * (i % 5) for i in range(40)]
    v = rsi([float(c) for c in closes], 14)
    assert 0.0 < v < 100.0


def test_atr_flat_is_zero():
    n = 20
    assert atr([100.0] * n, [100.0] * n, [100.0] * n, 14) == 0.0


def test_atr_positive_on_range():
    highs  = [101.0] * 20
    lows   = [99.0] * 20
    closes = [100.0] * 20
    assert atr(highs, lows, closes, 14) == pytest.approx(2.0)


def test_ema_converges_to_constant():
    assert ema([50.0] * 300, 200) == pytest.approx(50.0)


# ── Stratégie ─────────────────────────────────────────────────────

def test_not_enough_candles_returns_none():
    candles = make_candles([100.0] * (MIN_CANDLES - 1))
    assert analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0) is None


def _trending_candles_with_dip(hour=10, weekday_date="2026-07-15"):
    """Série haussière (close > EMA200) terminée par un plongeon sous la BB basse."""
    closes = [3000.0 + i * 0.5 for i in range(MIN_CANDLES + 40)]
    # plongeon final brutal : sous la bande basse, RSI écrasé, mais > EMA200
    for k, drop in enumerate([3.0, 6.0, 9.0, 12.0, 15.0]):
        closes[-5 + k] = closes[-6] - drop
    candles = []
    for c in closes:
        candles.append({
            "time":  f"{weekday_date}T{hour:02d}:00:00",
            "open":  c, "high": c + 0.5, "low": c - 0.5, "close": c,
        })
    return candles


def test_long_signal_on_dip_in_uptrend():
    candles = _trending_candles_with_dip()
    sig = analyse_meanrev("GOLD", GOLD_CFG, candles, risk_amount=500.0)
    assert sig is not None
    assert sig["direction"] == "BUY"
    assert sig["sl_price"] < sig["entry_price"] < sig["tp_price"]
    assert sig["symbol"] == GOLD_CFG["symbol"]


def test_signal_blocked_outside_session():
    candles = _trending_candles_with_dip(hour=23)
    assert analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0) is None


def test_signal_blocked_on_weekend():
    candles = _trending_candles_with_dip(weekday_date="2026-07-18")  # samedi
    assert analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0) is None


def test_qty_matches_risk():
    candles = _trending_candles_with_dip()
    risk = 500.0
    sig = analyse_meanrev("GOLD", GOLD_CFG, candles, risk_amount=risk)
    sl_dist = abs(sig["entry_price"] - sig["sl_price"])
    # qty (contrats) x taille contrat x distance SL ≈ montant risqué (à l'arrondi 0.1 près)
    risked = sig["qty"] * GOLD_CFG["contract_size"] * sl_dist
    assert risked == pytest.approx(risk, rel=0.35)
    assert sig["qty"] >= 0.1
    assert round(sig["qty"] * 10) == pytest.approx(sig["qty"] * 10)  # pas de 0.1


def test_tp_sl_ratio_is_tenth():
    candles = _trending_candles_with_dip()
    sig = analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0)
    tp_dist = abs(sig["tp_price"] - sig["entry_price"])
    sl_dist = abs(sig["sl_price"] - sig["entry_price"])
    assert tp_dist / sl_dist == pytest.approx(0.1, rel=0.05)  # 0.5 ATR vs 5 ATR


def test_no_signal_in_quiet_uptrend():
    closes = [3000.0 + i * 0.5 for i in range(MIN_CANDLES + 40)]
    candles = make_candles(closes)
    assert analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0) is None
