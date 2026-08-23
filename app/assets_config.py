# ──────────────────────────────────────────────────────────────────────────────
# assets_config.py — Asset configuration for ZorionBot (Alpaca Markets)
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
        # 2026-07-23 : "Or au comptant Mini (10oz)" (CS.D.CFDGOLD.CFM.IP) rejeté par
        # l'API IG démo (403 unauthorised access, exchangeId=GC_WORLD_USD — compte démo
        # sans accès à cet exchange group). Basculé sur "Spot Gold ($1)", même flux de
        # prix (spread identique, vérifié bid/offer), testé en réel (ordre + clôture OK).
        "symbol":        "CS.D.CFEGOLD.CEF.IP",  # Spot Gold ($1) — 1 contrat = 1$/point
        "contract_size": 1.0,
        "currency_code": "USD",
        "point_value":   1.0,
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
