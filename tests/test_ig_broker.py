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
