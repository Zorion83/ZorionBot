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
MR_TP_ATR     = float(os.environ.get("MR_TP_ATR", "0.5"))
MR_SL_ATR     = float(os.environ.get("MR_SL_ATR", "5.0"))
MR_TIME_STOP  = int(os.environ.get("MR_TIME_STOP", "16"))    # barres M30 (16 = 8h)
MR_TP1_ATR    = float(os.environ.get("MR_TP1_ATR", "1.0"))
MR_TP2_ATR    = float(os.environ.get("MR_TP2_ATR", "2.0"))
MR_TP3_ATR    = float(os.environ.get("MR_TP3_ATR", "3.0"))
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
