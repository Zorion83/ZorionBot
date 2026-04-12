"""
config.py — All configuration variables read from environment.
Copy .env.example → .env and fill in values before starting.
"""
import os

# ── Broker (Alpaca Markets) ───────────────────────────────────────
DEMO_MODE         = os.environ.get("DEMO_MODE", "true").lower() == "true"
ALPACA_API_KEY    = os.environ.get("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.environ.get("ALPACA_API_SECRET", "")

# ── Telegram ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Strategy ──────────────────────────────────────────────────────
DONCHIAN_LENGTH   = int(os.environ.get("DONCHIAN_LENGTH", "100"))
LOOKBACK_CANDLES  = int(os.environ.get("LOOKBACK_CANDLES", "500"))

# ── Risk ──────────────────────────────────────────────────────────
RISK_PCT     = float(os.environ.get("RISK_PCT", "0.005"))   # 0.5 % du solde par trade
POINT_VALUE  = float(os.environ.get("POINT_VALUE", "1.0"))
RR_RATIO     = float(os.environ.get("RR_RATIO", "2.0"))

# ── Logs ──────────────────────────────────────────────────────────
DATA_DIR  = os.environ.get("DATA_DIR", "/app/data")
LOG_FILE  = os.path.join(DATA_DIR, "donchianbot.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
