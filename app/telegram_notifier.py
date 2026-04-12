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
            f"Entry : {signal['entry_price']:.2f}\n"
            f"SL    : {signal['sl_price']:.2f}\n"
            f"TP    : {signal['tp_price']:.2f}\n"
            f"Size  : {signal['qty']:.2f}"
        )

    async def send_trade_closed(
        self, symbol: str, direction: str, pnl: float, demo: bool
    ) -> None:
        emoji        = "💰" if pnl >= 0 else "💸"
        result       = "WIN" if pnl >= 0 else "LOSS"
        direction_str = "LONG" if direction == "BUY" else "SHORT"
        mode_tag     = "[DEMO] " if demo else ""
        pnl_str      = f"{'+'if pnl >= 0 else ''}{pnl:.2f} $"
        await self._send(
            f"{emoji} <b>Trade closed {mode_tag}{symbol}</b>\n"
            f"Direction : {direction_str}\n"
            f"P&L       : {pnl_str}\n"
            f"Result    : <b>{result}</b>"
        )

    async def send_error(self, context: str, message: str) -> None:
        await self._send(f"❌ <b>Error — {context}</b>\n{message}")

    async def send_daily_summary(self, trades_today: int, open_positions: list) -> None:
        lines = [f"📊 <b>DonchianBot — Daily Summary</b>", f"Trades today: {trades_today}"]

        if open_positions:
            lines.append(f"\n<b>Open positions ({len(open_positions)}):</b>")
            for pos in open_positions:
                direction = "🚀 LONG" if pos["direction"] == "BUY" else "🔻 SHORT"
                pnl       = pos.get("unrealized_pl", 0)
                pnl_str   = f"{'+'if pnl >= 0 else ''}{pnl:.2f} $"
                entry     = pos.get("entry_price", 0)
                current   = pos.get("current_price", 0)
                lines.append(
                    f"• {direction} {pos['epic']}\n"
                    f"  Entry: {entry:.2f} → Now: {current:.2f}\n"
                    f"  P&L flottant: {pnl_str}"
                )
        else:
            lines.append("Open positions: 0")

        await self._send("\n".join(lines))
