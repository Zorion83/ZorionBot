import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import asyncio

import main as m
from config import MR_BREAKEVEN_BUFFER_ATR
from brokers.base_broker import BrokerError


class FakeBroker:
    """Stub broker — capture les appels amend_stop sans réseau réel."""

    def __init__(self, fail_deal_ids=None):
        self.calls = []
        self._fail_deal_ids = set(fail_deal_ids or [])

    async def amend_stop(self, deal_id, new_sl, tp=None):
        self.calls.append({"deal_id": deal_id, "new_sl": new_sl, "tp": tp})
        if deal_id in self._fail_deal_ids:
            raise BrokerError("amend rejected")


class FakeTelegram:
    """Stub telegram — capture les messages sans appel réseau réel."""

    def __init__(self):
        self.sent = []
        self.errors = []

    async def _send(self, text):
        self.sent.append(text)

    async def send_error(self, context, message):
        self.errors.append((context, message))


def _run(coro):
    return asyncio.run(coro)


class TestApplyBreakevenDirection:
    def test_buy_cache_entry_uses_entry_minus_buffer(self):
        m._signal_cache = {
            "T1": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 1, "sl": 4300.0, "tp": 4360.0},
            "T2": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 2, "sl": 4300.0, "tp": 4370.0},
        }
        broker   = FakeBroker()
        telegram = FakeTelegram()

        _run(m._apply_breakeven(
            broker, telegram, "GOLD", "T1", m._signal_cache["T1"], open_deal_ids={"T1", "T2"},
        ))

        expected_sl = 4350.0 - MR_BREAKEVEN_BUFFER_ATR * 10.0
        assert len(broker.calls) == 1
        assert broker.calls[0]["deal_id"] == "T2"
        assert broker.calls[0]["new_sl"] == expected_sl

    def test_sell_cache_entry_flips_sign(self):
        m._signal_cache = {
            "T1": {"epic": "GOLD", "direction": "SELL", "entry": 4350.0, "atr": 10.0,
                   "tier": 1, "sl": 4400.0, "tp": 4340.0},
            "T2": {"epic": "GOLD", "direction": "SELL", "entry": 4350.0, "atr": 10.0,
                   "tier": 2, "sl": 4400.0, "tp": 4330.0},
        }
        broker   = FakeBroker()
        telegram = FakeTelegram()

        _run(m._apply_breakeven(
            broker, telegram, "GOLD", "T1", m._signal_cache["T1"], open_deal_ids={"T1", "T2"},
        ))

        expected_sl = 4350.0 + MR_BREAKEVEN_BUFFER_ATR * 10.0
        assert broker.calls[0]["new_sl"] == expected_sl


class TestApplyBreakevenFiltering:
    def test_only_same_epic_open_and_not_closed_deal_get_amended(self):
        m._signal_cache = {
            "T1":        {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                          "tier": 1, "sl": 4300.0, "tp": 4360.0},
            "T2":        {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                          "tier": 2, "sl": 4300.0, "tp": 4370.0},
            "T3_CLOSED": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                          "tier": 3, "sl": 4300.0, "tp": 4380.0},
            "OTHER":     {"epic": "SILVER", "direction": "BUY", "entry": 30.0, "atr": 0.5,
                          "tier": 1, "sl": 29.0, "tp": 30.5},
        }
        broker   = FakeBroker()
        telegram = FakeTelegram()

        # T3_CLOSED a déjà fermé ce même cycle (time stop / TP1-3 dans la même bougie) :
        # il ne doit PAS être amendé même s'il matche epic + deal_id != closed_deal_id.
        _run(m._apply_breakeven(
            broker, telegram, "GOLD", "T1", m._signal_cache["T1"], open_deal_ids={"T1", "T2"},
        ))

        amended_ids = {c["deal_id"] for c in broker.calls}
        assert amended_ids == {"T2"}

    def test_no_siblings_sends_nothing(self):
        m._signal_cache = {
            "T1": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 1, "sl": 4300.0, "tp": 4360.0},
        }
        broker   = FakeBroker()
        telegram = FakeTelegram()

        _run(m._apply_breakeven(
            broker, telegram, "GOLD", "T1", m._signal_cache["T1"], open_deal_ids={"T1"},
        ))

        assert broker.calls == []
        assert telegram.sent == []

    def test_tp_preserved_from_sibling_cache(self):
        m._signal_cache = {
            "T1": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 1, "sl": 4300.0, "tp": 4360.0},
            "T2": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 2, "sl": 4300.0, "tp": 4370.0},
        }
        broker   = FakeBroker()
        telegram = FakeTelegram()

        _run(m._apply_breakeven(
            broker, telegram, "GOLD", "T1", m._signal_cache["T1"], open_deal_ids={"T1", "T2"},
        ))

        assert broker.calls[0]["tp"] == 4370.0   # TP propre au sibling T2, pas celui de T1


class TestApplyBreakevenCacheWriteback:
    def test_cache_sl_updated_after_successful_amend(self):
        m._signal_cache = {
            "T1": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 1, "sl": 4300.0, "tp": 4360.0},
            "T2": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 2, "sl": 4300.0, "tp": 4370.0},
        }
        broker   = FakeBroker()
        telegram = FakeTelegram()

        _run(m._apply_breakeven(
            broker, telegram, "GOLD", "T1", m._signal_cache["T1"], open_deal_ids={"T1", "T2"},
        ))

        expected_sl = 4350.0 - MR_BREAKEVEN_BUFFER_ATR * 10.0
        assert m._signal_cache["T2"]["sl"] == expected_sl

    def test_cache_sl_not_updated_when_amend_fails(self):
        m._signal_cache = {
            "T1": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 1, "sl": 4300.0, "tp": 4360.0},
            "T2": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 2, "sl": 4300.0, "tp": 4370.0},
        }
        broker   = FakeBroker(fail_deal_ids={"T2"})
        telegram = FakeTelegram()

        _run(m._apply_breakeven(
            broker, telegram, "GOLD", "T1", m._signal_cache["T1"], open_deal_ids={"T1", "T2"},
        ))

        assert m._signal_cache["T2"]["sl"] == 4300.0   # inchangé
        assert len(telegram.errors) == 1


class TestApplyBreakevenGuard:
    def test_returns_early_when_entry_missing(self):
        cache_entry = {"epic": "GOLD", "direction": "BUY", "entry": 0.0, "atr": 10.0}
        m._signal_cache = {
            "T1": cache_entry,
            "T2": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 2, "sl": 4300.0, "tp": 4370.0},
        }
        broker   = FakeBroker()
        telegram = FakeTelegram()

        _run(m._apply_breakeven(
            broker, telegram, "GOLD", "T1", cache_entry, open_deal_ids={"T1", "T2"},
        ))

        assert broker.calls == []

    def test_returns_early_when_atr_missing(self):
        cache_entry = {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 0.0}
        m._signal_cache = {
            "T1": cache_entry,
            "T2": {"epic": "GOLD", "direction": "BUY", "entry": 4350.0, "atr": 10.0,
                   "tier": 2, "sl": 4300.0, "tp": 4370.0},
        }
        broker   = FakeBroker()
        telegram = FakeTelegram()

        _run(m._apply_breakeven(
            broker, telegram, "GOLD", "T1", cache_entry, open_deal_ids={"T1", "T2"},
        ))

        assert broker.calls == []
