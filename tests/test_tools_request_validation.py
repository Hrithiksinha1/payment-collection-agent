from pathlib import Path
import sys
from datetime import datetime

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tools.lookup as lookup_module
import tools.payment as payment_module


class DummyResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_lookup_invalid_account_id_does_not_call_requests(monkeypatch):
    called = {"count": 0}

    def fake_post(*args, **kwargs):
        called["count"] += 1
        return DummyResponse(200, {})

    monkeypatch.setattr(lookup_module.requests, "post", fake_post)

    with pytest.raises(lookup_module.ToolError):
        lookup_module.lookup_account("bad-id")

    assert called["count"] == 0


def test_lookup_normalizes_account_id_before_request(monkeypatch):
    captured = {"payload": None}

    def fake_post(url, json, timeout):
        captured["payload"] = json
        return DummyResponse(200, {"account_id": "ACC1001"})

    monkeypatch.setattr(lookup_module.requests, "post", fake_post)

    result = lookup_module.lookup_account(" acc1001 ")

    assert captured["payload"] == {"account_id": "ACC1001"}
    assert result["account_id"] == "ACC1001"


def test_payment_invalid_amount_does_not_call_requests(monkeypatch):
    called = {"count": 0}

    def fake_post(*args, **kwargs):
        called["count"] += 1
        return DummyResponse(200, {})

    monkeypatch.setattr(payment_module.requests, "post", fake_post)

    with pytest.raises(payment_module.ToolError):
        payment_module.process_payment(
            account_id="ACC1001",
            amount=0,
            card={
                "cardholder_name": "Nithin Jain",
                "card_number": "4532015112830366",
                "cvv": "123",
                "expiry_month": 12,
                "expiry_year": 2099,
            },
        )

    assert called["count"] == 0


def test_payment_missing_card_field_does_not_call_requests(monkeypatch):
    called = {"count": 0}

    def fake_post(*args, **kwargs):
        called["count"] += 1
        return DummyResponse(200, {})

    monkeypatch.setattr(payment_module.requests, "post", fake_post)

    with pytest.raises(payment_module.ToolError):
        payment_module.process_payment(
            account_id="ACC1001",
            amount=5,
            card={
                "cardholder_name": "Nithin Jain",
                "card_number": "4532015112830366",
                "cvv": "123",
                "expiry_month": 12,
            },
        )

    assert called["count"] == 0


def test_payment_valid_input_calls_requests_with_normalized_payload(monkeypatch):
    valid_year = datetime.now().year + 1
    captured = {"payload": None}

    def fake_post(url, json, timeout):
        captured["payload"] = json
        return DummyResponse(200, {"transaction_id": "TXN123"})

    monkeypatch.setattr(payment_module.requests, "post", fake_post)

    result = payment_module.process_payment(
        account_id=" acc1001 ",
        amount="5.00",
        card={
            "cardholder_name": "  Nithin Jain  ",
            "card_number": "4532 0151 1283 0366",
            "cvv": "123",
            "expiry_month": "12",
            "expiry_year": str(valid_year),
        },
    )

    assert captured["payload"]["account_id"] == "ACC1001"
    assert captured["payload"]["amount"] == 5.0
    assert captured["payload"]["payment_method"]["card"]["card_number"] == "4532015112830366"
    assert result == {"success": True, "transaction_id": "TXN123"}
