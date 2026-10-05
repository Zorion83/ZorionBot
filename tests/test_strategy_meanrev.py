"""Tests de strategy_meanrev (signaux v5) et des nouveaux indicateurs."""
import math
from datetime import datetime, timezone

import pytest

from indicators import atr, bollinger, ema, rsi
from strategy_meanrev import MIN_CANDLES, analyse_meanrev

# Cycle 5 s après la clôture de la bougie 10:00 (mercredi 15/07/2026)
NOW = datetime(2026, 7, 15, 10, 30, 5, tzinfo=timezone.utc)

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
    assert analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0, now=NOW) is None


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
    sig = analyse_meanrev("GOLD", GOLD_CFG, candles, risk_amount=500.0, now=NOW)
    assert sig is not None
    assert sig["direction"] == "BUY"
    assert sig["sl_price"] < sig["entry_price"] < sig["tp_price"]
    assert sig["symbol"] == GOLD_CFG["symbol"]


def test_signal_blocked_outside_session():
    candles = _trending_candles_with_dip(hour=23)
    now = datetime(2026, 7, 15, 23, 30, 5, tzinfo=timezone.utc)
    assert analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0, now=now) is None


def test_signal_blocked_on_weekend():
    candles = _trending_candles_with_dip(weekday_date="2026-07-18")  # samedi
    now = datetime(2026, 7, 18, 10, 30, 5, tzinfo=timezone.utc)
    assert analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0, now=now) is None


# ── Bougie en cours / bougie périmée ──────────────────────────────

def _with_in_progress(candles, close):
    """Ajoute la bougie 10:30, ouverte depuis 5 s au moment de NOW."""
    return candles + [{
        "time": "2026-07-15T10:30:00",
        "open": close, "high": close, "low": close, "close": close,
    }]


def test_in_progress_candle_is_ignored():
    # La bougie 10:00 clôturée porte le signal ; la bougie en cours (remontée
    # dans la bande) ne doit pas l'effacer.
    candles = _trending_candles_with_dip()
    recovered = candles[-6]["close"]
    sig = analyse_meanrev("GOLD", GOLD_CFG, _with_in_progress(candles, recovered),
                          500.0, now=NOW)
    assert sig is not None
    assert sig["direction"] == "BUY"
    assert sig["entry_price"] == candles[-1]["close"]


def test_in_progress_candle_cannot_create_signal():
    # Tendance calme clôturée, plongeon uniquement dans la bougie en cours :
    # rien tant qu'elle n'est pas close, signal une fois qu'elle l'est.
    closes = [3000.0 + i * 0.5 for i in range(MIN_CANDLES + 40)]
    candles = [{"time": "2026-07-15T10:00:00", "open": c, "high": c + 0.5,
                "low": c - 0.5, "close": c} for c in closes]
    with_dip = _with_in_progress(candles, closes[-1] - 20.0)
    assert analyse_meanrev("GOLD", GOLD_CFG, with_dip, 500.0, now=NOW) is None

    closed = datetime(2026, 7, 15, 11, 0, 5, tzinfo=timezone.utc)
    sig = analyse_meanrev("GOLD", GOLD_CFG, with_dip, 500.0, now=closed)
    assert sig is not None and sig["direction"] == "BUY"


def test_stale_candle_over_weekend_is_refused():
    # Dernière bougie = vendredi 20:30, cycle le dimanche 22:00 : signal périmé.
    candles = _trending_candles_with_dip(hour=20, weekday_date="2026-07-17")
    now = datetime(2026, 7, 19, 22, 0, 5, tzinfo=timezone.utc)
    assert analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0, now=now) is None


def test_stale_candle_one_bar_late_is_refused():
    candles = _trending_candles_with_dip()
    now = datetime(2026, 7, 15, 11, 0, 6, tzinfo=timezone.utc)  # bougie 10:00 close depuis 30 min
    assert analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0, now=now) is None


def test_last_closed_candle_used_when_no_new_candle_yet():
    # Vendredi 21:00 : marché fermé, pas de bougie 21:00 ; la 20:30 vient de clôturer.
    candles = _trending_candles_with_dip(hour=20, weekday_date="2026-07-17")
    for c in candles:
        c["time"] = "2026-07-17T20:30:00"
    now = datetime(2026, 7, 17, 21, 0, 5, tzinfo=timezone.utc)
    sig = analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0, now=now)
    assert sig is not None


def test_qty_matches_risk():
    candles = _trending_candles_with_dip()
    risk = 500.0
    sig = analyse_meanrev("GOLD", GOLD_CFG, candles, risk_amount=risk, now=NOW)
    sl_dist = abs(sig["entry_price"] - sig["sl_price"])
    # qty (contrats) x taille contrat x distance SL ≈ montant risqué (à l'arrondi 0.1 près)
    risked = sig["qty"] * GOLD_CFG["contract_size"] * sl_dist
    assert risked == pytest.approx(risk, rel=0.35)
    assert sig["qty"] >= 0.1
    assert round(sig["qty"] * 10) == pytest.approx(sig["qty"] * 10)  # pas de 0.1


def test_tp_sl_ratio_is_tenth():
    candles = _trending_candles_with_dip()
    sig = analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0, now=NOW)
    tp_dist = abs(sig["tp_price"] - sig["entry_price"])
    sl_dist = abs(sig["sl_price"] - sig["entry_price"])
    assert tp_dist / sl_dist == pytest.approx(0.1, rel=0.05)  # 0.5 ATR vs 5 ATR


def test_signal_includes_atr():
    candles = _trending_candles_with_dip()
    sig = analyse_meanrev("GOLD", GOLD_CFG, candles, risk_amount=500.0, now=NOW)
    assert sig["atr"] > 0.0


def test_no_signal_in_quiet_uptrend():
    closes = [3000.0 + i * 0.5 for i in range(MIN_CANDLES + 40)]
    candles = make_candles(closes)
    assert analyse_meanrev("GOLD", GOLD_CFG, candles, 500.0, now=NOW) is None
