"""
telegram_notifier.py — Async Telegram notifications.
If TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty, notifications are silently disabled.
"""
import logging
import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:

    def __init__(self, token: str, chat_id: str):
        self._token   = token
        self._chat_id = chat_id
        self._enabled = bool(token and chat_id)

    async def _send(self, text: str) -> None:
        if not self._enabled:
            logger.debug("Telegram disabled (missing token/chat_id)")
            return
        url = TELEGRAM_API.format(token=self._token)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json={
                    "chat_id":    self._chat_id,
                    "text":       text,
                    "parse_mode": "HTML",
                })
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)

    async def send_test_message(self) -> None:
        await self._send("✅ DonchianBot connected and operational.")

    async def send_startup(self, demo: bool, assets: list) -> None:
        mode       = "DEMO" if demo else "LIVE ⚠️"
        assets_str = ", ".join(assets) if assets else "no assets configured"
        await self._send(
            f"🤖 <b>DonchianBot started</b>\n"
            f"Mode: {mode}\n"
            f"Assets: {assets_str}"
        )

    async def send_signal(self, signal: dict, demo: bool) -> None:
        direction = "🚀 LONG" if signal["direction"] == "BUY" else "🔻 SHORT"
        mode_tag  = "[DEMO] " if demo else ""
        await self._send(
            f"{direction} {mode_tag}<b>{signal['asset_name']}</b>\n"
            f"Entry: {signal['entry_price']:.2f}\n"
            f"SL: {signal['sl_price']:.2f}\n"
            f"TP: {signal['tp_price']:.2f}\n"
            f"Size: {signal['qty']:.2f}"
        )

    async def send_error(self, context: str, message: str) -> None:
        await self._send(f"❌ <b>Error — {context}</b>\n{message}")

    async def send_daily_summary(self, trades_today: int, open_positions: list) -> None:
        await self._send(
            f"📊 <b>DonchianBot Daily Summary</b>\n"
            f"Trades today: {trades_today}\n"
            f"Open positions: {len(open_positions)}"
        )
