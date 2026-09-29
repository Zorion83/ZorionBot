"""
config.py — All configuration variables read from environment.
Copy .env.example → .env and fill in values before starting.
"""
import os

# ── Broker ────────────────────────────────────────────────────────
BROKER            = os.environ.get("BROKER", "ig").lower()   # "ig" | "alpaca"
DEMO_MODE         = os.environ.get("DEMO_MODE", "true").lower() == "true"
ALPACA_API_KEY    = os.environ.get("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.environ.get("ALPACA_API_SECRET", "")

# ── IG Markets ────────────────────────────────────────────────────
IG_API_KEY    = os.environ.get("IG_API_KEY", "")
IG_IDENTIFIER = os.environ.get("IG_IDENTIFIER", "")
IG_PASSWORD   = os.environ.get("IG_PASSWORD", "")

# ── Telegram ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
# ID du topic (message_thread_id) dans un groupe Telegram en mode "Sujets".
# Vide = messages postés dans le topic "Général" (comportement historique, chat privé inclus).
TELEGRAM_THREAD_ID  = int(os.environ["TELEGRAM_THREAD_ID"]) if os.environ.get("TELEGRAM_THREAD_ID") else None

# ── Strategy (héritage Donchian) ──────────────────────────────────
DONCHIAN_LENGTH   = int(os.environ.get("DONCHIAN_LENGTH", "100"))
LOOKBACK_CANDLES  = int(os.environ.get("LOOKBACK_CANDLES", "500"))

# ── Strategy Mean Reversion XAUUSD v5 ─────────────────────────────
MR_BB_LEN     = int(os.environ.get("MR_BB_LEN", "20"))
MR_BB_STD     = float(os.environ.get("MR_BB_STD", "1.5"))
MR_RSI_LEN    = int(os.environ.get("MR_RSI_LEN", "14"))
MR_RSI_LO     = float(os.environ.get("MR_RSI_LO", "40"))
MR_EMA_LEN    = int(os.environ.get("MR_EMA_LEN", "200"))
MR_ATR_LEN    = int(os.environ.get("MR_ATR_LEN", "14"))
# TP 1.0xATR / time stop 96 barres (48h) : retenu le 2026-09-19 après backtest
# Dukascopy 2025-01->2026-09 (net +3579$, PF 1.46, robuste 2025 ET 2026 sous le
# vrai spread IG mesuré à 1.0$/oz) contre le scaling 3 paliers (meilleur palier
# testé : +2883$, PF 1.38) — position unique retenue, scaling abandonné.
MR_TP_ATR     = float(os.environ.get("MR_TP_ATR", "1.0"))
MR_SL_ATR     = float(os.environ.get("MR_SL_ATR", "5.0"))
MR_TIME_STOP  = int(os.environ.get("MR_TIME_STOP", "96"))    # barres M30 (96 = 48h)
MR_BREAKEVEN_BUFFER_ATR = float(os.environ.get("MR_BREAKEVEN_BUFFER_ATR", "0.2"))
MR_SESS_START = int(os.environ.get("MR_SESS_START", "5"))    # heure UTC
MR_SESS_END   = int(os.environ.get("MR_SESS_END", "22"))

# ── Risk ──────────────────────────────────────────────────────────
RISK_PCT     = float(os.environ.get("RISK_PCT", "0.005"))   # 0.5 % du solde par trade
POINT_VALUE  = float(os.environ.get("POINT_VALUE", "1.0"))
RR_RATIO     = float(os.environ.get("RR_RATIO", "2.0"))

# ── Logs ──────────────────────────────────────────────────────────
DATA_DIR  = os.environ.get("DATA_DIR", "/app/data")
LOG_FILE  = os.path.join(DATA_DIR, "zorionbot.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
