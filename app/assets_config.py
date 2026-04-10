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
    "SP500": {
        "symbol":      "SPY",   # SPDR S&P 500 ETF Trust
        "point_value": 1.0,
        "rr_ratio":    2.0,
        "enabled":     True,
    },
    "QQQ": {
        "symbol":      "QQQ",   # Invesco QQQ Trust (Nasdaq 100)
        "point_value": 1.0,
        "rr_ratio":    2.0,
        "enabled":     True,
    },
}

ENABLED_ASSETS = {k: v for k, v in ASSETS.items() if v.get("enabled", False)}
