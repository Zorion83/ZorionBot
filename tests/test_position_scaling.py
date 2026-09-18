import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from position_scaling import build_scaled_orders

BASE_SIGNAL = {
    "direction":   "BUY",
    "entry_price": 4350.0,
    "sl_price":    4300.0,   # distance 50 == 5 x atr(10)
    "atr":         10.0,
    "asset_name":  "GOLD",
    "symbol":      "CS.D.CFEGOLD.CEF.IP",
}


def test_returns_three_orders():
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=558.69, contract_size=1.0)
    assert len(orders) == 3
    assert [o["tier"] for o in orders] == [1, 2, 3]


def test_tp_levels_are_1_2_3x_atr_for_long():
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=558.69, contract_size=1.0)
    entry, atr_val = BASE_SIGNAL["entry_price"], BASE_SIGNAL["atr"]
    assert orders[0]["tp_price"] == pytest.approx(entry + 1 * atr_val)
    assert orders[1]["tp_price"] == pytest.approx(entry + 2 * atr_val)
    assert orders[2]["tp_price"] == pytest.approx(entry + 3 * atr_val)


def test_tp_levels_go_down_for_short():
    signal = {**BASE_SIGNAL, "direction": "SELL", "sl_price": 4400.0}
    orders = build_scaled_orders(signal, risk_amount=558.69, contract_size=1.0)
    entry, atr_val = signal["entry_price"], signal["atr"]
    assert orders[0]["tp_price"] == pytest.approx(entry - 1 * atr_val)
    assert orders[2]["tp_price"] == pytest.approx(entry - 3 * atr_val)


def test_same_entry_and_sl_across_tiers():
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=558.69, contract_size=1.0)
    for o in orders:
        assert o["entry_price"] == BASE_SIGNAL["entry_price"]
        assert o["sl_price"] == BASE_SIGNAL["sl_price"]


def test_risk_split_equally_across_tiers():
    risk_amount = 558.69
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=risk_amount, contract_size=1.0)
    sl_dist = abs(BASE_SIGNAL["entry_price"] - BASE_SIGNAL["sl_price"])
    total_risked = sum(o["qty"] * sl_dist * 1.0 for o in orders)
    assert total_risked == pytest.approx(risk_amount, rel=0.1)
    assert len({o["qty"] for o in orders}) == 1   # tailles égales


def test_qty_respects_01_step_minimum():
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=1.0, contract_size=1.0)
    for o in orders:
        assert o["qty"] >= 0.1


def test_zero_sl_distance_returns_empty():
    signal = {**BASE_SIGNAL, "sl_price": BASE_SIGNAL["entry_price"]}
    assert build_scaled_orders(signal, risk_amount=500.0, contract_size=1.0) == []


def test_custom_tp_multipliers():
    orders = build_scaled_orders(
        BASE_SIGNAL, risk_amount=558.69, contract_size=1.0,
        tp_atr_multipliers=(0.5, 1.5),
    )
    assert len(orders) == 2
    entry, atr_val = BASE_SIGNAL["entry_price"], BASE_SIGNAL["atr"]
    assert orders[0]["tp_price"] == pytest.approx(entry + 0.5 * atr_val)
    assert orders[1]["tp_price"] == pytest.approx(entry + 1.5 * atr_val)


def test_asset_name_and_symbol_carried_through():
    orders = build_scaled_orders(BASE_SIGNAL, risk_amount=558.69, contract_size=1.0)
    for o in orders:
        assert o["asset_name"] == "GOLD"
        assert o["symbol"] == "CS.D.CFEGOLD.CEF.IP"
