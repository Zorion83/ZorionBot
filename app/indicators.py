"""
indicators.py — Pure technical indicator calculations.

Candle indexing convention:
  candles[-1]  = signal candle (last closed candle)
  candles[-2]  = previous candle
  candles[-3]  = the one before that

No external dependencies.
"""


def heiken_ashi(opens: list, highs: list, lows: list, closes: list) -> tuple:
    """
    Compute Heiken Ashi OHLC series from raw candle data.

    HA Close = (O + H + L + C) / 4
    HA Open  = (prev HA Open + prev HA Close) / 2  [recursive; seed = (O[0]+C[0])/2]
    HA High  = max(High, HA Open, HA Close)
    HA Low   = min(Low,  HA Open, HA Close)

    Returns:
        (ha_opens, ha_highs, ha_lows, ha_closes) — four lists of floats, same length as inputs
    """
    n = len(opens)
    if n == 0:
        raise ValueError("heiken_ashi: inputs must not be empty")
    if not (n == len(highs) == len(lows) == len(closes)):
        raise ValueError(
            f"heiken_ashi: all input lists must have the same length "
            f"(got {n}, {len(highs)}, {len(lows)}, {len(closes)})"
        )

    ha_closes = [(opens[i] + highs[i] + lows[i] + closes[i]) / 4.0 for i in range(n)]

    ha_opens = [0.0] * n
    ha_opens[0] = (opens[0] + closes[0]) / 2.0
    for i in range(1, n):
        ha_opens[i] = (ha_opens[i - 1] + ha_closes[i - 1]) / 2.0

    ha_highs = [max(highs[i], ha_opens[i], ha_closes[i]) for i in range(n)]
    ha_lows  = [min(lows[i],  ha_opens[i], ha_closes[i]) for i in range(n)]

    return ha_opens, ha_highs, ha_lows, ha_closes


def _ema_series(values: list, period: int) -> list:
    """
    Compute the full EMA series for a list of values.
    Initialisation: first result = first element of the list.
    """
    k = 2.0 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def donchian_channel(highs: list, lows: list, length: int) -> tuple:
    """
    Compute Donchian channel levels over the last `length` candles.

    Returns:
        (upper, lower, basis, limitHigh, limitLow)
        - upper     : highest high over `length` candles
        - lower     : lowest low over `length` candles
        - basis     : midpoint of the channel
        - limitHigh : upper quartile (Q3) — sell zone
        - limitLow  : lower quartile (Q1) — buy zone
    """
    if length <= 0:
        raise ValueError("length must be positive")
    if len(highs) < length or len(lows) < length:
        raise ValueError(f"donchian_channel requires at least {length} candles, got {min(len(highs), len(lows))}")
    if len(highs) != len(lows):
        raise ValueError(f"highs and lows must have the same length (got {len(highs)} and {len(lows)})")
    upper = max(highs[-length:])
    lower = min(lows[-length:])
    basis = (upper + lower) / 2.0
    limitHigh = upper - (upper - basis) / 2.0
    limitLow  = lower + (basis - lower) / 2.0
    return upper, lower, basis, limitHigh, limitLow


def zlmacd(closes: list, fast: int = 12, slow: int = 26) -> float:
    """
    Zero Lag MACD = DEMA(fast) - DEMA(slow)
    DEMA(n) = 2 × EMA(close, n) - EMA(EMA(close, n), n)

    Only the MACD line value is returned.
    The signal line and histogram are intentionally omitted —
    the strategy only uses zlmacd > 0 / < 0.

    Args:
        closes: List of closing prices (min slow × 2 = 52 values)
        fast:   Fast period (default: 12)
        slow:   Slow period (default: 26)

    Raises:
        ValueError: if the list is too short to compute ZL-MACD
    """
    min_required = slow * 2
    if len(closes) < min_required:
        raise ValueError(
            f"zlmacd requires at least {min_required} values, "
            f"{len(closes)} provided."
        )

    # DEMA fast
    ema1     = _ema_series(closes, fast)
    ema2     = _ema_series(ema1, fast)
    demaFast = 2.0 * ema1[-1] - ema2[-1]

    # DEMA slow
    emas1    = _ema_series(closes, slow)
    emas2    = _ema_series(emas1, slow)
    demaSlow = 2.0 * emas1[-1] - emas2[-1]

    return demaFast - demaSlow
