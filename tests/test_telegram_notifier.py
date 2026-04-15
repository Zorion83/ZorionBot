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


class TestFormatOpenPosition:
    def _make_pos(self, direction="BUY", entry=83500.0, current=84200.0, pnl=210.5):
        return {
            "epic":          "BTC/USD",
            "direction":     direction,
            "entry_price":   entry,
            "current_price": current,
            "unrealized_pl": pnl,
        }

    def test_shows_number_and_symbol(self):
        from telegram_notifier import _format_open_position
        result = _format_open_position(1, self._make_pos(), cache_entry=None)
        assert "#1" in result
        assert "BTC/USD" in result

    def test_long_label(self):
        from telegram_notifier import _format_open_position
        result = _format_open_position(1, self._make_pos("BUY"), cache_entry=None)
        assert "LONG" in result

    def test_short_label(self):
        from telegram_notifier import _format_open_position
        result = _format_open_position(1, self._make_pos("SELL"), cache_entry=None)
        assert "SHORT" in result

    def test_no_cache_shows_na(self):
        from telegram_notifier import _format_open_position
        result = _format_open_position(1, self._make_pos(), cache_entry=None)
        assert "N/A" in result

    def test_cache_shows_sl_tp(self):
        from telegram_notifier import _format_open_position
        cache = {"sl": 81000.0, "tp": 88500.0, "direction": "BUY"}
        result = _format_open_position(1, self._make_pos(), cache_entry=cache)
        assert "81000" in result
        assert "88500" in result

    def test_long_progress_calculation(self):
        from telegram_notifier import _format_open_position
        # entry=0, current=5, tp=10 → 50%
        pos   = self._make_pos(entry=0.0, current=5.0)
        cache = {"sl": -1.0, "tp": 10.0, "direction": "BUY"}
        result = _format_open_position(1, pos, cache_entry=cache)
        assert "50%" in result

    def test_short_progress_calculation(self):
        from telegram_notifier import _format_open_position
        # entry=10, current=5, tp=0 → 50%
        pos   = self._make_pos("SELL", entry=10.0, current=5.0, pnl=5.0)
        cache = {"sl": 11.0, "tp": 0.0, "direction": "SELL"}
        result = _format_open_position(1, pos, cache_entry=cache)
        assert "50%" in result

    def test_progress_capped_at_100(self):
        from telegram_notifier import _format_open_position
        # current déjà au-delà du TP
        pos   = self._make_pos(entry=0.0, current=15.0)
        cache = {"sl": -1.0, "tp": 10.0, "direction": "BUY"}
        result = _format_open_position(1, pos, cache_entry=cache)
        assert "100%" in result
