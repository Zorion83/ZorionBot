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

    def test_no_progress_when_tp_equals_entry(self):
        from telegram_notifier import _format_open_position
        pos   = self._make_pos(entry=100.0, current=110.0)
        cache = {"sl": 90.0, "tp": 100.0, "direction": "BUY"}
        result = _format_open_position(1, pos, cache_entry=cache)
        assert "90" in result    # SL shown
        assert "100" in result   # TP shown
        assert "%" not in result  # no progress line


def test_format_open_position_shows_tier_tag():
    from telegram_notifier import _format_open_position
    pos = {"epic": "CS.D.CFEGOLD.CEF.IP", "direction": "BUY",
           "entry_price": 4350.0, "current_price": 4355.0, "unrealized_pl": 5.0}
    cache_entry = {"sl": 4300.0, "tp": 4360.0, "tier": 2}
    text = _format_open_position(1, pos, cache_entry)
    assert "Position 2/3" in text


def test_format_open_position_no_tag_without_tier():
    from telegram_notifier import _format_open_position
    pos = {"epic": "SPY", "direction": "BUY",
           "entry_price": 500.0, "current_price": 501.0, "unrealized_pl": 1.0}
    cache_entry = {"sl": 495.0, "tp": 510.0}   # pas de "tier" (chemin Alpaca legacy)
    text = _format_open_position(1, pos, cache_entry)
    assert "Position" not in text.split("SL")[0].split("\n")[0] or "/3" not in text


class TestTradeNumbering:
    """Numéro de trade global + entrée/SL/TP/écart en points/lot dans chaque message."""

    ORDER = {
        "direction": "SELL", "asset_name": "GOLD", "tier": 1,
        "entry_price": 4171.38, "sl_price": 4226.28, "tp_price": 4160.40, "qty": 10.5,
    }

    def _capture(self, t):
        captured = []
        async def fake_send(text): captured.append(text)
        t._send = fake_send
        return captured

    def test_signal_shows_trade_no_levels_points_and_lot(self):
        t = TelegramNotifier("token", "chat")
        captured = self._capture(t)
        asyncio.run(t.send_signal(self.ORDER, demo=True, trade_no=34))
        text = captured[0]
        assert "#34" in text
        assert "4171.38" in text and "4226.28" in text and "4160.40" in text
        assert "-549.0 pips" in text         # SL : 54.90 $ de cours contre le trade
        assert "+109.8 pips" in text         # TP : 10.98 $ de cours en faveur du trade
        assert "-576.45 $" in text           # 549 pips x 10.5 lots x 0.10 $/pip
        assert "10.5" in text
        assert "1.05 $/pip" in text          # valeur d'un pip pour ce lot
        assert "1 pip = 0.10" in text        # rappel de la conversion

    def test_signal_without_trade_no_still_works(self):
        t = TelegramNotifier("token", "chat")
        captured = self._capture(t)
        asyncio.run(t.send_signal(self.ORDER, demo=False))
        assert "GOLD" in captured[0]
        assert "#" not in captured[0]

    def test_trade_closed_shows_trade_no_and_details(self):
        t = TelegramNotifier("token", "chat")
        captured = self._capture(t)
        asyncio.run(t.send_trade_closed(
            "GOLD", "SELL", 115.29, demo=True, trade_no=34,
            entry=4171.38, exit_price=4160.40, sl=4226.28, tp=4160.40, qty=10.5,
        ))
        text = captured[0]
        assert "#34" in text
        assert "4171.38" in text and "4160.40" in text and "4226.28" in text
        assert "+109.8 pips" in text
        assert "10.5" in text
        assert "+115.29 $" in text
        assert "1 pip = 0.10" in text

    def test_trade_closed_minimal_call_still_works(self):
        t = TelegramNotifier("token", "chat")
        captured = self._capture(t)
        asyncio.run(t.send_trade_closed("GOLD", "BUY", -12.0, demo=False))
        assert "LOSS" in captured[0]
        assert "SL / TP" not in captured[0]

    def test_open_position_uses_trade_no_and_shows_lot(self):
        from telegram_notifier import _format_open_position
        pos = {"epic": "CS.D.CFEGOLD.CEF.IP", "direction": "SELL", "size": 10.5,
               "entry_price": 4171.38, "current_price": 4165.88}
        cache = {"sl": 4226.28, "tp": 4160.40, "qty": 10.5, "trade_no": 34,
                 "asset_name": "GOLD"}
        text = _format_open_position(1, pos, cache)
        assert "#34" in text
        assert "GOLD" in text
        assert "+55.0 pips" in text
        assert "+57.75 $" in text            # P&L recalculé : 5.50 x 10.5
        assert "Lot" in text


class TestSendDailySummaryExtended:
    def test_closed_today_section_appears(self):
        """send_daily_summary doit afficher la section trades clôturés si non vide."""
        t = TelegramNotifier("token", "chat")
        captured = []
        async def fake_send(text): captured.append(text)
        t._send = fake_send

        closed_today = [
            {"id": 1, "symbol": "BTC/USD", "direction": "BUY",
             "pnl": 210.5, "closed_at": "2026-04-16T10:30:00Z"},
        ]
        open_positions = []
        signal_cache   = {}
        asyncio.run(t.send_daily_summary(1, open_positions, closed_today, signal_cache))

        assert len(captured) == 1
        assert "#1" in captured[0]
        assert "BTC/USD" in captured[0]
        assert "+210.50" in captured[0]

    def test_no_closed_today_section_when_empty(self):
        """Pas de section clôtures si aucun trade aujourd'hui."""
        t = TelegramNotifier("token", "chat")
        captured = []
        async def fake_send(text): captured.append(text)
        t._send = fake_send

        asyncio.run(t.send_daily_summary(0, [], [], {}))
        assert "clôturés" not in captured[0]

    def test_open_positions_use_format_helper(self):
        """Les positions ouvertes passent par _format_open_position."""
        t = TelegramNotifier("token", "chat")
        captured = []
        async def fake_send(text): captured.append(text)
        t._send = fake_send

        pos = {
            "epic": "BTC/USD", "deal_id": "DEAL-1", "direction": "BUY",
            "entry_price": 83500.0, "current_price": 84200.0, "unrealized_pl": 210.5,
        }
        cache = {"sl": 81000.0, "tp": 88500.0, "direction": "BUY"}
        asyncio.run(t.send_daily_summary(0, [pos], [], {"DEAL-1": cache}))
        assert "#1" in captured[0]
        assert "81000" in captured[0]   # SL visible
