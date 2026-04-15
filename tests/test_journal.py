import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from unittest.mock import patch
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
        m.DATA_DIR = str(tmp_path)
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
