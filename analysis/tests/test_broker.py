import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from broker import Broker, PaperBroker


def test_paper_broker_produces_a_filled_receipt():
    intent = {"id": "abc-123", "code": "SAMPLE1", "side": "BUY", "quantity": 5}

    receipt = PaperBroker().submit(intent)

    assert receipt["status"] == "PAPER_FILLED"
    assert receipt["broker"] == "paper"
    assert receipt["brokerOrderId"] == "paper-abc-123"
    assert receipt["submittedAt"]
    # Original intent fields are preserved, not dropped.
    assert receipt["code"] == "SAMPLE1"
    assert receipt["quantity"] == 5


def test_broker_is_an_abstract_interface():
    with pytest.raises(TypeError):
        Broker()
