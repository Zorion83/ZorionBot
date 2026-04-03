import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from strategy import analyse_asset


def _make_candles(n=200):
    """Generate neutral candles that let haOpen converge to 100."""
    return [{"open": 100.0, "high": 109.0, "low": 91.0, "close": 100.0} for _ in range(n)]


def _set_long_conditions(candles):
    """
    Configure last 3 candles to trigger a LONG signal (Heiken Ashi logic).

    After 197 neutral candles at O=C=100, H=109, L=91, haOpen converges to 100.

    candles[-3]: raw low=89 → haLow = min(89, haOpen≈100, haClose≈90.75) = 89 ≤ lower=89 ✓
    candles[-2]: haOpen[-2]=(100+90.75)/2=95.375 ; haClose[-2]=91 ; haHigh[-2]=95.375
    candles[-1]: haOpen[-1]=(95.375+91)/2=93.19 < limitLow=94 ✓
                 haClose[-1]=97 > haHigh[-2]=95.375 ✓  (bullish HA)

    Donchian (length=100): upper=109, lower=89, limitLow=94
    Entry = raw high[-2]=93 ; SL = min(raw low[-1], raw low[-2])=89 ; TP=101
    """
    # Keep neutral candles (haOpen converges to 100)
    # [-3]: haLow touches lower band
    candles[-3] = {"open": 91.0, "high": 92.0, "low": 89.0, "close": 91.0}
    # [-2]: bridge candle — haOpen[-2]=95.375, haClose[-2]=91, haHigh[-2]=95.375
    candles[-2] = {"open": 91.0, "high": 93.0, "low": 89.0, "close": 91.0}
    # [-1]: signal candle — haOpen[-1]=93.19 < limitLow=94, haClose[-1]=97 > haHigh[-2]=95.375
    candles[-1] = {"open": 91.0, "high": 105.0, "low": 89.0, "close": 103.0}


def _set_short_conditions(candles):
    """
    Configure last 3 candles to trigger a SHORT signal (Heiken Ashi logic).

    After 197 neutral candles at O=C=100, H=109, L=91, haOpen converges to 100.

    candles[-3]: raw high=111 → haHigh = max(111, haOpen≈100, haClose≈109.25) = 111 ≥ upper=111 ✓
    candles[-2]: haOpen[-2]=(100+109.25)/2=104.625 ; haClose[-2]=109 ; haLow[-2]=104.625
    candles[-1]: haOpen[-1]=(104.625+109)/2=106.81 > limitHigh=106 ✓
                 haClose[-1]=103 < haLow[-2]=104.625 ✓  (bearish HA)

    Donchian (length=100): upper=111, lower=91, limitHigh=106
    Entry = raw low[-2]=107 ; SL = max(raw high[-1], raw high[-2])=111 ; TP=99
    """
    # [-3]: haHigh touches upper band
    candles[-3] = {"open": 109.0, "high": 111.0, "low": 108.0, "close": 109.0}
    # [-2]: bridge candle — haOpen[-2]=104.625, haClose[-2]=109, haLow[-2]=104.625
    candles[-2] = {"open": 109.0, "high": 111.0, "low": 107.0, "close": 109.0}
    # [-1]: signal candle — haOpen[-1]=106.81 > limitHigh=106, haClose[-1]=103 < haLow[-2]=104.625
    candles[-1] = {"open": 109.0, "high": 111.0, "low": 95.0, "close": 97.0}


class TestAnalyseAssetLong:
    def test_long_signal_all_conditions_met(self):
        candles = _make_candles(200)
        _set_long_conditions(candles)

        # ZL-MACD must be < 0 for LONG: downtrend across all candles except last 3
        for i in range(len(candles) - 3):
            candles[i]["close"] = 120.0 - i * 0.1

        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset(
            "TEST", asset_config, candles,
            prev_long=False, prev_short=False,
            risk_amount=50.0, donchian_length=100
        )
        assert result is not None
        assert result["direction"] == "BUY"
        assert result["entry_price"] > 0
        assert result["sl_price"] > 0
        assert result["tp_price"] > result["entry_price"]
        assert result["qty"] > 0

    def test_no_signal_when_prev_long_true(self):
        """Anti-doublon: no LONG signal if previous candle was also LONG."""
        candles = _make_candles(200)
        _set_long_conditions(candles)
        for i in range(len(candles) - 3):
            candles[i]["close"] = 120.0 - i * 0.1

        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset(
            "TEST", asset_config, candles,
            prev_long=True, prev_short=False,
            risk_amount=50.0, donchian_length=100
        )
        assert result is None

    def test_no_signal_insufficient_candles(self):
        candles = _make_candles(10)
        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset(
            "TEST", asset_config, candles,
            prev_long=False, prev_short=False,
            risk_amount=50.0, donchian_length=100
        )
        assert result is None


class TestAnalyseAssetShort:
    def test_short_signal_all_conditions_met(self):
        candles = _make_candles(200)
        _set_short_conditions(candles)

        # ZL-MACD must be > 0 for SHORT: uptrend across all candles except last 3
        for i in range(len(candles) - 3):
            candles[i]["close"] = 80.0 + i * 0.1

        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset(
            "TEST", asset_config, candles,
            prev_long=False, prev_short=False,
            risk_amount=50.0, donchian_length=100
        )
        assert result is not None
        assert result["direction"] == "SELL"
        assert result["tp_price"] < result["entry_price"]

    def test_no_signal_when_prev_short_true(self):
        """Anti-doublon: no SHORT signal if previous candle was also SHORT."""
        candles = _make_candles(200)
        _set_short_conditions(candles)
        for i in range(len(candles) - 3):
            candles[i]["close"] = 80.0 + i * 0.1

        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset(
            "TEST", asset_config, candles,
            prev_long=False, prev_short=True,
            risk_amount=50.0, donchian_length=100
        )
        assert result is None
