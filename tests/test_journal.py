import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from datetime import datetime, timezone



class TestJournalRotation:
    def test_no_rotation_same_month(self, tmp_path):
        current = datetime.now(timezone.utc).strftime("%Y-%m")
        journal = {"month": current, "next_id": 2, "trades": [{"id": 1}]}
        journal_file = tmp_path / "trade_journal.json"
        journal_file.write_text(json.dumps(journal))

        import main as m
        m._JOURNAL_FILE = str(journal_file)
        result = m._rotate_journal_if_needed(journal)

        assert result["month"] == current
        assert result["next_id"] == 2          # inchangé
        assert len(list(tmp_path.glob("trade_journal_2???-??.json"))) == 0

    def test_rotation_on_new_month(self, tmp_path):
        old_month = "2025-01"
        journal = {"month": old_month, "next_id": 4, "trades": [{"id": 3}]}

        import main as m
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        result = m._rotate_journal_if_needed(journal)

        current = datetime.now(timezone.utc).strftime("%Y-%m")
        assert result["month"] == current
        assert result["next_id"] == 1
        assert result["trades"] == []
        archive = tmp_path / f"trade_journal_{old_month}.json"
        assert archive.exists()
        archived = json.loads(archive.read_text())
        assert archived["month"] == old_month


class TestJournalAddTrade:
    def test_first_trade_gets_id_1(self, tmp_path):
        import main as m
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        journal = {"month": "2026-04", "next_id": 1, "trades": []}

        trade_id = m._add_to_journal(
            journal,
            symbol="BTC/USD", asset_name="Bitcoin", direction="BUY",
            entry_price=83500.0, exit_price=84200.0,
            sl_price=81000.0, tp_price=88500.0,
            qty=0.002, pnl=1.4,
            closed_at="2026-04-16T14:30:00Z",
        )

        assert trade_id == 1
        assert journal["next_id"] == 2
        assert len(journal["trades"]) == 1
        assert journal["trades"][0]["id"] == 1
        assert journal["trades"][0]["symbol"] == "BTC/USD"

    def test_second_trade_gets_id_2(self, tmp_path):
        import main as m
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        journal = {"month": "2026-04", "next_id": 1, "trades": []}

        m._add_to_journal(journal, "BTC/USD", "Bitcoin", "BUY",
                          83500.0, 84200.0, 81000.0, 88500.0, 0.002, 1.4,
                          "2026-04-16T10:00:00Z")
        trade_id = m._add_to_journal(journal, "SPY", "SPY ETF", "SELL",
                                     500.0, 495.0, 505.0, 490.0, 1.0, 5.0,
                                     "2026-04-16T14:00:00Z")

        assert trade_id == 2
        assert journal["next_id"] == 3
        assert len(journal["trades"]) == 2

    def test_trade_stores_tier(self, tmp_path):
        import main as m
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        journal = {"month": "2026-04", "next_id": 1, "trades": []}

        m._add_to_journal(
            journal, symbol="CS.D.CFEGOLD.CEF.IP", asset_name="GOLD", direction="BUY",
            entry_price=4350.0, exit_price=4360.0, sl_price=4300.0, tp_price=4360.0,
            qty=0.4, pnl=4.0, closed_at="2026-09-18T10:00:00Z", tier=1,
        )

        assert journal["trades"][0]["tier"] == 1


class TestTradeNumber:
    def test_allocates_and_persists_increasing_numbers(self, tmp_path):
        import main as m
        m._STATE_FILE = str(tmp_path / "bot_state.json")
        (tmp_path / "bot_state.json").write_text(json.dumps({"next_trade_no": 34}))

        assert m._allocate_trade_no() == 34
        assert m._allocate_trade_no() == 35
        assert json.loads((tmp_path / "bot_state.json").read_text())["next_trade_no"] == 36

    def test_starts_at_1_without_state(self, tmp_path):
        import main as m
        m._STATE_FILE = str(tmp_path / "bot_state.json")
        assert m._allocate_trade_no() == 1

    def test_journal_stores_trade_no(self, tmp_path):
        import main as m
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        journal = {"month": "2026-09", "next_id": 5, "trades": []}
        m._add_to_journal(
            journal, symbol="CS.D.CFEGOLD.CEF.IP", asset_name="GOLD", direction="SELL",
            entry_price=4171.38, exit_price=4160.40, sl_price=4226.28, tp_price=4160.40,
            qty=10.5, pnl=115.29, closed_at="2026-09-30T10:00:00Z", tier=1, trade_no=34,
        )
        assert journal["trades"][0]["trade_no"] == 34
        assert journal["trades"][0]["id"] == 5


class TestAdoptUnknownPositions:
    """Position ouverte chez IG mais inconnue du bot (confirmation perdue) : on la
    reprend avec les vrais SL/TP IG, le nom d'actif et un numéro de trade."""

    def test_adopts_position_missing_from_cache(self, tmp_path):
        import main as m
        m._STATE_FILE = str(tmp_path / "bot_state.json")
        (tmp_path / "bot_state.json").write_text(json.dumps({"next_trade_no": 34}))
        m._signal_cache.clear()
        pos = {"epic": "CS.D.CFEGOLD.CEF.IP", "deal_id": "DEAL9", "direction": "SELL",
               "size": 12.4, "entry_price": 4153.12, "sl": 4199.3, "tp": 4143.88,
               "created_at": "2026-09-29T11:00:05"}

        adopted = m._adopt_unknown_positions([pos])

        assert len(adopted) == 1
        entry = m._signal_cache["DEAL9"]
        assert entry["asset_name"] == "GOLD"
        assert entry["sl"] == 4199.3 and entry["tp"] == 4143.88
        assert entry["trade_no"] == 34
        assert entry["opened_at"] == "2026-09-29T11:00:05"
        m._signal_cache.clear()

    def test_ignores_known_positions(self, tmp_path):
        import main as m
        m._STATE_FILE = str(tmp_path / "bot_state.json")
        m._signal_cache.clear()
        m._signal_cache["DEAL1"] = {"trade_no": 7}
        pos = {"epic": "CS.D.CFEGOLD.CEF.IP", "deal_id": "DEAL1", "direction": "BUY",
               "size": 1, "entry_price": 1.0, "sl": 0.5, "tp": 1.5, "created_at": ""}

        assert m._adopt_unknown_positions([pos]) == []
        assert m._signal_cache["DEAL1"] == {"trade_no": 7}
        m._signal_cache.clear()


class TestLoadJournal:
    def test_returns_fresh_journal_when_file_missing(self, tmp_path):
        import main as m
        m._JOURNAL_FILE = str(tmp_path / "trade_journal.json")
        journal = m._load_journal()

        current = datetime.now(timezone.utc).strftime("%Y-%m")
        assert journal["month"] == current
        assert journal["next_id"] == 1
        assert journal["trades"] == []

    def test_loads_existing_journal(self, tmp_path):
        current = datetime.now(timezone.utc).strftime("%Y-%m")
        data = {"month": current, "next_id": 5, "trades": [{"id": 4}]}
        jfile = tmp_path / "trade_journal.json"
        jfile.write_text(json.dumps(data))

        import main as m
        m._JOURNAL_FILE = str(jfile)
        journal = m._load_journal()

        assert journal["next_id"] == 5
        assert len(journal["trades"]) == 1
