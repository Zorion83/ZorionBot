import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import main as m

LONG_CACHE = {"direction": "BUY", "tp": 4360.0, "sl": 4300.0, "tier": 1}


def test_matches_transaction_closest_to_tp():
    candidates = [
        {"side": "sell", "filled_avg_price": 4300.5, "pnl": -50.0},  # proche du SL
        {"side": "sell", "filled_avg_price": 4359.8, "pnl": 10.0},   # proche du TP
    ]
    match = m._match_closed_deal("BUY", LONG_CACHE, candidates)
    assert match["filled_avg_price"] == 4359.8


def test_ignores_wrong_closing_side():
    candidates = [
        {"side": "buy", "filled_avg_price": 4359.8, "pnl": 10.0},   # mauvais camp (ouverture, pas clôture)
    ]
    assert m._match_closed_deal("BUY", LONG_CACHE, candidates) is None


def test_no_candidates_returns_none():
    assert m._match_closed_deal("BUY", LONG_CACHE, []) is None


def test_short_direction_closing_side_is_buy():
    cache = {"direction": "SELL", "tp": 4300.0, "sl": 4360.0, "tier": 1}
    candidates = [{"side": "buy", "filled_avg_price": 4300.2, "pnl": 20.0}]
    match = m._match_closed_deal("SELL", cache, candidates)
    assert match is not None


def test_degenerate_case_two_deals_same_sl_still_matches_one():
    # Positions 2 et 3 fermées ensemble sur le même SL : les deux candidats sont
    # équidistants du SL, la fonction doit renvoyer l'un des deux sans erreur.
    cache_tier2 = {"direction": "BUY", "tp": 4370.0, "sl": 4300.0, "tier": 2}
    candidates = [
        {"side": "sell", "filled_avg_price": 4300.0, "pnl": -186.0},
        {"side": "sell", "filled_avg_price": 4300.0, "pnl": -186.0},
    ]
    match = m._match_closed_deal("BUY", cache_tier2, candidates)
    assert match is not None
    assert match["filled_avg_price"] == 4300.0
