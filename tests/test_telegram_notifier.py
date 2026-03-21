import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram_notifier import TelegramNotifier


class TestTelegramNotifierInit:
    def test_disabled_when_token_empty(self):
        t = TelegramNotifier("", "12345")
        assert not t._enabled

    def test_disabled_when_chat_id_empty(self):
        t = TelegramNotifier("token", "")
        assert not t._enabled

    def test_disabled_when_both_empty(self):
        t = TelegramNotifier("", "")
        assert not t._enabled

    def test_enabled_when_both_provided(self):
        t = TelegramNotifier("bot123:TOKEN", "-100123456")
        assert t._enabled


class TestTelegramNotifierSend:
    def test_send_does_not_raise_when_disabled(self):
        t = TelegramNotifier("", "")
        # Should not raise even when called
        asyncio.run(t._send("test message"))

    def test_send_does_not_raise_on_network_error(self):
        """_send must swallow all exceptions — never crash the bot."""
        t = TelegramNotifier("bad_token", "bad_chat")
        # Patch httpx to raise a connection error
        with patch("telegram_notifier.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post.side_effect = Exception("Network unreachable")
            mock_client.return_value = mock_instance
            # Should NOT raise
            asyncio.run(t._send("test"))

    def test_send_signal_buy(self):
        """send_signal formats BUY correctly."""
        t = TelegramNotifier("token", "chat")
        signal = {
            "direction":   "BUY",
            "asset_name":  "DAX",
            "entry_price": 18000.0,
            "sl_price":    17950.0,
            "tp_price":    18100.0,
            "qty":         1.0,
        }
        captured = []
        async def fake_send(text):
            captured.append(text)
        t._send = fake_send

        asyncio.run(t.send_signal(signal, demo=True))
        assert len(captured) == 1
        assert "LONG" in captured[0]
        assert "[DEMO]" in captured[0]
        assert "DAX" in captured[0]

    def test_send_signal_sell(self):
        """send_signal formats SELL correctly."""
        t = TelegramNotifier("token", "chat")
        signal = {
            "direction":   "SELL",
            "asset_name":  "DAX",
            "entry_price": 18000.0,
            "sl_price":    18050.0,
            "tp_price":    17900.0,
            "qty":         1.0,
        }
        captured = []
        async def fake_send(text):
            captured.append(text)
        t._send = fake_send

        asyncio.run(t.send_signal(signal, demo=False))
        assert "SHORT" in captured[0]
        assert "[DEMO]" not in captured[0]
