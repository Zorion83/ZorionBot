import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from indicators import donchian_channel, zlmacd, heiken_ashi


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


class TestHeikenAshi:
    def test_first_candle_values(self):
        # haOpen[0] = (O+C)/2 = (100+103)/2 = 101.5
        # haClose[0] = (O+H+L+C)/4 = (100+105+95+103)/4 = 100.75
        # haHigh[0] = max(105, 101.5, 100.75) = 105
        # haLow[0]  = min(95, 101.5, 100.75) = 95
        ha_opens, ha_highs, ha_lows, ha_closes = heiken_ashi(
            [100.0], [105.0], [95.0], [103.0]
        )
        assert ha_opens[0]  == pytest.approx(101.5)
        assert ha_closes[0] == pytest.approx(100.75)
        assert ha_highs[0]  == pytest.approx(105.0)
        assert ha_lows[0]   == pytest.approx(95.0)

    def test_second_candle_open_is_recursive(self):
        # haOpen[1] = (haOpen[0] + haClose[0]) / 2 = (101.5 + 100.75) / 2 = 101.125
        ha_opens, _, _, ha_closes = heiken_ashi(
            [100.0, 102.0], [105.0, 108.0], [95.0, 98.0], [103.0, 106.0]
        )
        assert ha_opens[1] == pytest.approx(101.125)

    def test_convergence_after_many_identical_candles(self):
        """After many identical candles haOpen converges to haClose."""
        n = 200
        ha_opens, _, _, ha_closes = heiken_ashi(
            [100.0] * n, [101.0] * n, [99.0] * n, [100.0] * n
        )
        assert ha_closes[-1] == pytest.approx(100.0)
        assert abs(ha_opens[-1] - 100.0) < 0.001

    def test_raises_on_empty_input(self):
        with pytest.raises(ValueError):
            heiken_ashi([], [], [], [])

    def test_raises_on_mismatched_lengths(self):
        with pytest.raises(ValueError):
            heiken_ashi([100.0] * 3, [101.0] * 3, [99.0] * 3, [100.0] * 2)
