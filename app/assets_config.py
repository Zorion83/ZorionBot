# ──────────────────────────────────────────────────────────────────────────────
# assets_config.py — Asset configuration for DonchianBot (Alpaca Markets)
#
# Required fields per asset:
#   "symbol"      : Ticker Alpaca (ex: "SPY", "QQQ")
#
#   "point_value" : Valeur d'un point en devise du compte (USD)
#                   → Pour les ETFs US : 1.0 (1 action = 1 point = $1)
#                   → Surcharge la valeur globale POINT_VALUE du .env
#
#   "rr_ratio"    : Ratio Risque/Rendement pour le Take Profit
#                   → Surcharge la valeur globale RR_RATIO du .env
#                   → Exemple : 2.0 = TP placé à 2× la distance du SL
#
#   "enabled"     : True = actif surveillé, False = ignoré
#
# Priority rule: la valeur par actif est prioritaire sur la valeur globale .env
# ──────────────────────────────────────────────────────────────────────────────

ASSETS = {
    # ── Stratégie Mean Reversion v5 sur IG Markets ────────────────
    "GOLD": {
        "symbol":        "CS.D.CFDGOLD.CFM.IP",  # Or au comptant Mini (10 oz/contrat)
        "contract_size": 10.0,                   # 1 contrat = 10 oz ; 1 point = 1 $/oz
        "currency_code": "USD",
        "point_value":   10.0,                   # $ par point et par contrat
        "enabled":       True,
        "crypto":        False,
    },
    # ── Héritage Alpaca (désactivés depuis le passage à IG) ───────
    "SP500": {
        "symbol":      "SPY",
        "point_value": 1.0,
        "rr_ratio":    2.0,
        "enabled":     False,
        "crypto":      False,
    },
    "QQQ": {
        "symbol":      "QQQ",
        "point_value": 1.0,
        "rr_ratio":    2.0,
        "enabled":     False,
        "crypto":      False,
    },
    "BTC": {
        "symbol":      "BTC/USD",
        "point_value": 1.0,
        "rr_ratio":    2.0,
        "enabled":     False,
        "crypto":      True,
    },
}

ENABLED_ASSETS = {k: v for k, v in ASSETS.items() if v.get("enabled", False)}
