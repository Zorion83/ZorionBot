# ──────────────────────────────────────────────────────────────────────────────
# assets_config.py — Asset configuration for DonchianBot
#
# Fill this file with the assets to monitor before starting the bot.
#
# Required fields per asset:
#   "symbol"      : IG Markets epic for the instrument
#                   → Find it in the IG interface: click a market
#                     then "Information" > "Epic"
#                   Examples:
#                     DAX      → "IX.D.DAX.IFMM.IP"
#                     NAS100   → "IX.D.NASDAQ.IFD.IP"
#                     Gold CFD → "CS.D.CFEGOLD.CFE.IP"
#
#   "point_value" : Value of one point in account currency
#                   → Overrides the global POINT_VALUE from .env
#                   → Check the IG product details for this value
#                   Examples: 1.0 (standard CFD), 25.0 (DAX Mini)
#
#   "rr_ratio"    : Risk/Reward ratio for Take Profit
#                   → Overrides the global RR_RATIO from .env
#                   Example: 2.0 → TP placed at 2× SL distance
#
#   "enabled"     : True = asset monitored, False = ignored
#
# Priority rule: if "point_value" or "rr_ratio" is set in the asset dict,
# it overrides the global value from .env; otherwise the global value is used.
# ──────────────────────────────────────────────────────────────────────────────

ASSETS = {
    # Example (modify/replace with your assets):
    # "DAX": {
    #     "symbol":      "IX.D.DAX.IFMM.IP",
    #     "point_value": 1.0,
    #     "rr_ratio":    2.0,
    #     "enabled":     False,
    # },
}

ENABLED_ASSETS = {k: v for k, v in ASSETS.items() if v.get("enabled", False)}
