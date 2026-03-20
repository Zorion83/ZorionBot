"""
risk.py — Pure risk management calculations.
No external dependencies. Fully testable without a broker.
"""


def calculate_size(risk_amount: float, entry: float, sl: float, point_value: float) -> float:
    """
    Calculate position size to risk exactly risk_amount.

    Args:
        risk_amount:  Max amount to risk (e.g. 50.0 €)
        entry:        Entry price
        sl:           Stop loss price
        point_value:  Value of one point in account currency

    Returns:
        Number of units/lots to trade. 0.0 if distance is zero.
    """
    distance = abs(entry - sl)
    if distance == 0:
        return 0.0
    return risk_amount / (distance * point_value)


def calculate_tp(entry: float, sl: float, rr_ratio: float, direction: str) -> float:
    """
    Calculate Take Profit using R:R ratio.

    Args:
        entry:     Entry price
        sl:        Stop loss price
        rr_ratio:  Risk/reward ratio (e.g. 2.0 → TP at 2× SL distance)
        direction: "BUY" or "SELL"

    Returns:
        Take profit price.
    """
    distance = abs(entry - sl)
    if direction == "BUY":
        return entry + distance * rr_ratio
    elif direction == "SELL":
        return entry - distance * rr_ratio
    else:
        raise ValueError(f"Invalid direction '{direction}'. Expected 'BUY' or 'SELL'.")
