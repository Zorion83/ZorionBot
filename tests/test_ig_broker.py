import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import asyncio
import json

import httpx

from brokers.ig_broker import IGBroker


def _make_broker_with_transport(handler):
    """Broker IG avec son client httpx remplacé par un MockTransport (pas de réseau réel)."""
    broker = IGBroker("key", "id", "pwd", demo=True)
    broker._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    # Évite le re-login automatique sur 401 : simule une session déjà authentifiée.
    broker._cst   = "cst-token"
    broker._token = "sec-token"
    return broker


class TestAmendStop:
    def test_sends_put_to_positions_otc_with_stop_level(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"]    = str(request.url)
            captured["body"]   = json.loads(request.content)
            return httpx.Response(200, json={})

        broker = _make_broker_with_transport(handler)
        asyncio.run(broker.amend_stop("DEAL123", 4310.5))

        assert captured["method"] == "PUT"
        assert captured["url"].endswith("/positions/otc/DEAL123")
        assert captured["body"]["stopLevel"] == "4310.5"
        assert "limitLevel" not in captured["body"]

    def test_includes_limit_level_when_tp_given(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={})

        broker = _make_broker_with_transport(handler)
        asyncio.run(broker.amend_stop("DEAL123", 4310.5, tp=4400.0))

        assert captured["body"]["stopLevel"]  == "4310.5"
        assert captured["body"]["limitLevel"] == "4400.0"

    def test_omits_limit_level_when_tp_is_none(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={})

        broker = _make_broker_with_transport(handler)
        asyncio.run(broker.amend_stop("DEAL456", 100.0, tp=None))

        assert "limitLevel" not in captured["body"]


class TestConfirmRetry:
    """IG renvoie parfois 404 error.service.execution.find sur /confirms juste après
    un ordre exécuté (vu le 19/08, 25/09 et 29/09) : le dealId ne doit pas être perdu."""

    NOT_FOUND = {"errorCode": "error.service.execution.find"}

    @staticmethod
    def _no_delay(monkeypatch):
        import brokers.ig_broker as igb
        monkeypatch.setattr(igb, "CONFIRM_RETRY_DELAYS", (0, 0))

    def _positions(self, deal_ref, deal_id):
        return {"positions": [{
            "market":   {"epic": "CS.D.CFEGOLD.CEF.IP", "bid": 1.0, "offer": 1.1},
            "position": {"dealId": deal_id, "dealReference": deal_ref,
                         "direction": "SELL", "size": 1, "level": 1.0},
        }]}

    def test_retries_confirm_after_404(self, monkeypatch):
        self._no_delay(monkeypatch)
        calls = {"confirms": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/positions/otc"):
                return httpx.Response(200, json={"dealReference": "REF1"})
            if "/confirms/" in request.url.path:
                calls["confirms"] += 1
                if calls["confirms"] < 2:
                    return httpx.Response(404, json=self.NOT_FOUND)
                return httpx.Response(200, json={"dealStatus": "ACCEPTED", "dealId": "DEAL1"})
            return httpx.Response(500)

        broker = _make_broker_with_transport(handler)
        deal_id = asyncio.run(broker.open_short("CS.D.CFEGOLD.CEF.IP", 1, 2.0, 0.5))

        assert deal_id == "DEAL1"
        assert calls["confirms"] == 2

    def test_records_fill_level_from_confirm(self, monkeypatch):
        self._no_delay(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/positions/otc"):
                return httpx.Response(200, json={"dealReference": "REF5"})
            return httpx.Response(200, json={"dealStatus": "ACCEPTED", "dealId": "DEAL5",
                                             "level": 4171.09})

        broker = _make_broker_with_transport(handler)
        asyncio.run(broker.open_short("CS.D.CFEGOLD.CEF.IP", 1, 2.0, 0.5))

        assert broker.last_fill_level == 4171.09

    def test_falls_back_to_positions_when_confirm_keeps_failing(self, monkeypatch):
        self._no_delay(monkeypatch)
        calls = {"confirms": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and request.url.path.endswith("/positions/otc"):
                return httpx.Response(200, json={"dealReference": "REF2"})
            if "/confirms/" in request.url.path:
                calls["confirms"] += 1
                return httpx.Response(404, json=self.NOT_FOUND)
            if request.method == "GET" and request.url.path.endswith("/positions"):
                return httpx.Response(200, json=self._positions("REF2", "DEAL2"))
            return httpx.Response(500)

        broker = _make_broker_with_transport(handler)
        deal_id = asyncio.run(broker.open_short("CS.D.CFEGOLD.CEF.IP", 1, 2.0, 0.5))

        assert deal_id == "DEAL2"
        assert calls["confirms"] == 3
        assert broker.last_fill_level == 1.0     # "level" de la position IG

    def test_returns_empty_when_deal_not_found_anywhere(self, monkeypatch):
        self._no_delay(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and request.url.path.endswith("/positions/otc"):
                return httpx.Response(200, json={"dealReference": "REF3"})
            if "/confirms/" in request.url.path:
                return httpx.Response(404, json=self.NOT_FOUND)
            if request.method == "GET" and request.url.path.endswith("/positions"):
                return httpx.Response(200, json=self._positions("OTHER", "DEAL9"))
            return httpx.Response(500)

        broker = _make_broker_with_transport(handler)
        deal_id = asyncio.run(broker.open_short("CS.D.CFEGOLD.CEF.IP", 1, 2.0, 0.5))

        assert deal_id == ""

    def test_rejected_deal_still_raises_without_retry(self, monkeypatch):
        self._no_delay(monkeypatch)
        from brokers.base_broker import BrokerError
        calls = {"confirms": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/positions/otc"):
                return httpx.Response(200, json={"dealReference": "REF4"})
            if "/confirms/" in request.url.path:
                calls["confirms"] += 1
                return httpx.Response(200, json={"dealStatus": "REJECTED",
                                                 "reason": "INSUFFICIENT_FUNDS"})
            return httpx.Response(500)

        broker = _make_broker_with_transport(handler)
        try:
            asyncio.run(broker.open_short("CS.D.CFEGOLD.CEF.IP", 1, 2.0, 0.5))
            assert False, "BrokerError attendue"
        except BrokerError as e:
            assert "INSUFFICIENT_FUNDS" in str(e)
        assert calls["confirms"] == 1
