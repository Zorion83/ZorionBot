import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from risk import calculate_size, calculate_tp


class TestCalculateSize:
    def test_normal_case(self):
        # 50€ risk, 10pt distance, 1€/pt → 5 units
        assert calculate_size(50.0, 100.0, 90.0, 1.0) == pytest.approx(5.0)

    def test_point_value_multiplier(self):
        # 50€ risk, 2pt distance, 25€/pt → 1 unit
        assert calculate_size(50.0, 100.0, 98.0, 25.0) == pytest.approx(1.0)

    def test_zero_distance_returns_zero(self):
        # SL == entry → no trade possible
        assert calculate_size(50.0, 100.0, 100.0, 1.0) == 0.0

    def test_short_direction(self):
        # entry < sl for short → same result (uses abs)
        assert calculate_size(50.0, 90.0, 100.0, 1.0) == pytest.approx(5.0)


class TestCalculateTp:
    def test_buy_tp_above_entry(self):
        # entry=100, sl=90, rr=2 → tp=120
        assert calculate_tp(100.0, 90.0, 2.0, "BUY") == pytest.approx(120.0)

    def test_sell_tp_below_entry(self):
        # entry=100, sl=110, rr=2 → tp=80
        assert calculate_tp(100.0, 110.0, 2.0, "SELL") == pytest.approx(80.0)

    def test_rr_ratio_one(self):
        # rr=1 → TP = entry + distance (1:1)
        assert calculate_tp(100.0, 95.0, 1.0, "BUY") == pytest.approx(105.0)
