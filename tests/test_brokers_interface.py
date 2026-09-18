import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from brokers.ig_broker import IGBroker
from brokers.alpaca_broker import AlpacaBroker


def test_ig_broker_implements_full_interface():
    # Échoue à l'instanciation (TypeError) si une méthode abstraite manque.
    broker = IGBroker("key", "id", "pwd", demo=True)
    assert hasattr(broker, "amend_stop")
    assert hasattr(broker, "close_position")


def test_alpaca_broker_implements_full_interface():
    broker = AlpacaBroker("key", "secret", demo=True)
    assert hasattr(broker, "amend_stop")
    assert hasattr(broker, "close_position")
