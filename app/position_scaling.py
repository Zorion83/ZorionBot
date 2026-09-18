"""
position_scaling.py — Split a single trading signal into N sized sub-orders
(scaled take-profits), each carrying an equal share of the total risk.
"""
from typing import Dict, List, Sequence

DEFAULT_TP_ATR_MULTIPLIERS = (1.0, 2.0, 3.0)


def build_scaled_orders(
    signal: Dict,
    risk_amount: float,
    contract_size: float,
    tp_atr_multipliers: Sequence[float] = DEFAULT_TP_ATR_MULTIPLIERS,
) -> List[Dict]:
    """
    Split `signal` (a dict as returned by analyse_meanrev(), must include "atr")
    into len(tp_atr_multipliers) sub-orders sharing the same entry/SL, each with
    its own TP at `multiplier x ATR` from entry, and an equal share of risk_amount.

    Returns a list of dicts (empty if inputs are invalid), each with keys:
      tier, direction, entry_price, sl_price, tp_price, qty, asset_name, symbol
    """
    direction = signal["direction"]
    entry     = signal["entry_price"]
    sl        = signal["sl_price"]
    atr_val   = signal["atr"]
    sign      = 1 if direction == "BUY" else -1

    sl_dist = abs(entry - sl)
    if sl_dist <= 0 or risk_amount <= 0 or not tp_atr_multipliers:
        return []

    risk_per_tier = risk_amount / len(tp_atr_multipliers)
    qty = risk_per_tier / (sl_dist * contract_size)
    qty = max(round(qty, 1), 0.1)

    orders = []
    for tier, multiplier in enumerate(tp_atr_multipliers, start=1):
        tp_price = entry + sign * multiplier * atr_val
        orders.append({
            "tier":        tier,
            "direction":   direction,
            "entry_price": entry,
            "sl_price":    sl,
            "tp_price":    round(tp_price, 2),
            "qty":         qty,
            "asset_name":  signal["asset_name"],
            "symbol":      signal["symbol"],
        })
    return orders
