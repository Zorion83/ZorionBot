import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from strategy import analyse_asset


def _make_candles(n=200, base=100.0):
    """Generate neutral candles (open=close, symmetric high/low)."""
    return [{"open": base, "high": base + 1, "low": base - 1, "close": base} for _ in range(n)]


def _set_long_conditions(candles, upper, lower, limitLow, limitHigh):
    """
    Configure last 3 candles to trigger a LONG signal.
    LONG = price touches the LOWER band, then bounces up.
    candles[-3]: low touches lower band
    candles[-2]: neutral (high known for close > high[-2] test)
    candles[-1]: signal candle — bullish, close > high[-2], open < limitLow
    """
    base = (upper + lower) / 2
    for i in range(len(candles) - 3):
        candles[i] = {"open": base, "high": upper - 1, "low": lower + 1, "close": base}

    # candles[-3]: touches lower band (low <= lower)
    candles[-3] = {"open": lower + 2, "high": lower + 3, "low": lower, "close": lower + 2}
    # candles[-2]: neutral, high = base + 0.5 (known reference for close > high[-2])
    candles[-2] = {"open": base, "high": base + 0.5, "low": base - 1, "close": base}
    # candles[-1]: signal candle — bullish, open < limitLow, close > high[-2]
    candles[-1] = {
        "open":  limitLow - 1,   # open < limitLow ✓
        "high":  limitLow + 2,
        "low":   limitLow - 2,
        "close": base + 1,        # close > high[-2]=base+0.5 ✓ and close > open ✓
    }


def _set_short_conditions(candles, upper, lower, limitLow, limitHigh):
    """
    Configure last 3 candles to trigger a SHORT signal.
    SHORT = price touches the UPPER band, then reverses.
    candles[-3]: high touches upper band
    candles[-2]: neutral (low known for close < low[-2] test)
    candles[-1]: signal candle — bearish, close < low[-2], open > limitHigh
    """
    base = (upper + lower) / 2
    for i in range(len(candles) - 3):
        candles[i] = {"open": base, "high": upper - 1, "low": lower + 1, "close": base}

    # candles[-3]: touches upper band (high >= upper)
    candles[-3] = {"open": upper - 2, "high": upper, "low": upper - 3, "close": upper - 2}
    # candles[-2]: neutral, low = base - 0.5
    candles[-2] = {"open": base, "high": base + 1, "low": base - 0.5, "close": base}
    # candles[-1]: signal candle — bearish, open > limitHigh, close < low[-2]
    candles[-1] = {
        "open":  limitHigh + 1,  # open > limitHigh ✓
        "high":  limitHigh + 2,
        "low":   limitHigh - 2,
        "close": base - 1,        # close < low[-2]=base-0.5 ✓ and close < open ✓
    }


class TestAnalyseAssetLong:
    def test_long_signal_all_conditions_met(self):
        candles = _make_candles(200, base=100.0)
        upper, lower = 110.0, 90.0
        limitLow  = 95.0
        limitHigh = 105.0

        _set_long_conditions(candles, upper, lower, limitLow, limitHigh)

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
        candles = _make_candles(200, base=100.0)
        upper, lower = 110.0, 90.0
        _set_long_conditions(candles, upper, lower, 95.0, 105.0)
        for i in range(150):
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
        candles = _make_candles(200, base=100.0)
        upper, lower = 110.0, 90.0
        limitLow  = 95.0
        limitHigh = 105.0

        _set_short_conditions(candles, upper, lower, limitLow, limitHigh)

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
        candles = _make_candles(200, base=100.0)
        upper, lower = 110.0, 90.0
        _set_short_conditions(candles, upper, lower, 95.0, 105.0)
        for i in range(150):
            candles[i]["close"] = 80.0 + i * 0.1

        asset_config = {"symbol": "TEST.EPIC", "point_value": 1.0, "rr_ratio": 2.0}
        result = analyse_asset(
            "TEST", asset_config, candles,
            prev_long=False, prev_short=True,
            risk_amount=50.0, donchian_length=100
        )
        assert result is None
