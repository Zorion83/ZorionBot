import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from indicators import donchian_channel, zlmacd


class TestDonchianChannel:
    def test_upper_lower_basis(self):
        highs = [10.0] * 98 + [15.0, 12.0]   # last 100: max=15
        lows  = [5.0]  * 98 + [4.0, 6.0]      # last 100: min=4
        upper, lower, basis, limitHigh, limitLow = donchian_channel(highs, lows, 100)
        assert upper == pytest.approx(15.0)
        assert lower == pytest.approx(4.0)
        assert basis == pytest.approx(9.5)

    def test_quartiles(self):
        highs = [100.0] * 100
        lows  = [0.0]   * 100
        upper, lower, basis, limitHigh, limitLow = donchian_channel(highs, lows, 100)
        # basis=50, limitHigh=75, limitLow=25
        assert limitHigh == pytest.approx(75.0)
        assert limitLow  == pytest.approx(25.0)

    def test_uses_only_last_n_candles(self):
        # First 50 candles have high=999 — must NOT be included in length=50 calculation
        highs = [999.0] * 50 + [10.0] * 50
        lows  = [0.0]   * 100
        upper, lower, basis, limitHigh, limitLow = donchian_channel(highs, lows, 50)
        assert upper == pytest.approx(10.0)

    def test_raises_when_too_few_candles(self):
        with pytest.raises(ValueError):
            donchian_channel([10.0] * 5, [5.0] * 5, 10)  # length > list size

    def test_raises_when_lists_differ_in_length(self):
        with pytest.raises(ValueError):
            donchian_channel([10.0] * 10, [5.0] * 8, 5)  # mismatched lengths


class TestZlMacd:
    def _make_trend(self, start, step, n=200):
        """Generate a linear price series."""
        return [start + i * step for i in range(n)]

    def test_uptrend_returns_positive(self):
        closes = self._make_trend(100.0, 0.5)   # uptrend
        result = zlmacd(closes)
        assert result > 0

    def test_downtrend_returns_negative(self):
        closes = self._make_trend(200.0, -0.5)  # downtrend
        result = zlmacd(closes)
        assert result < 0

    def test_flat_returns_near_zero(self):
        closes = [100.0] * 200                   # flat price
        result = zlmacd(closes)
        assert abs(result) < 0.01

    def test_requires_sufficient_candles(self):
        with pytest.raises(ValueError):
            zlmacd([100.0] * 10)   # too few candles (min 52)
