import pytest
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent.agent as agent_module
from agent.agent import Agent, TERMINATED

@pytest.fixture
def verified_agent(monkeypatch):
    agent = Agent()
    def fake_lookup(account_id):
        return {"account_id": "ACC1001", "full_name": "Nithin Jain", "dob": "1990-05-14", "balance": 1000.0}
    monkeypatch.setattr(agent_module, "lookup_account", fake_lookup)
    
    # State sequence to reach PAYMENT_COLLECTION
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"account_id": "ACC1001"}))
    agent.next("ACC1001")
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"name": "Nithin Jain"}))
    agent.next("Nithin Jain")
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"name": "Nithin Jain", "dob": "1990-05-14"}))
    agent.next("1990-05-14")
    
    assert agent.ctx.state == agent_module.PAYMENT_COLLECTION
    return agent

def test_payment_insufficient_balance(monkeypatch, verified_agent):
    def fake_call_llm(system, messages):
        # Provide ALL fields so it hits the amount validator
        return json.dumps({
            "amount": 2000, 
            "card_number": "4532015112830366", "cvv": "123", 
            "expiry_month": 12, "expiry_year": 2030, "cardholder_name": "Nithin"
        })
    monkeypatch.setattr(agent_module, "call_llm", fake_call_llm)

    verified_agent.next("I want to pay 2000")
    
    assert "amount" not in verified_agent.ctx.collected # Should be cleared by validator
    assert verified_agent.ctx.last_error is not None
    assert "exceeds" in verified_agent.ctx.last_error.lower()

def test_payment_invalid_card_luhn(monkeypatch, verified_agent):
    def fake_call_llm(system, messages):
        return json.dumps({
            "amount": 100, "card_number": "1234567812345678", # Fails Luhn
            "cvv": "123", "expiry_month": 12, "expiry_year": 2030, "cardholder_name": "Nithin"
        })
    monkeypatch.setattr(agent_module, "call_llm", fake_call_llm)

    verified_agent.next("Pay with bad card")
    
    assert "card_number" not in verified_agent.ctx.collected
    assert verified_agent.ctx.last_error is not None
    assert "invalid" in verified_agent.ctx.last_error.lower()

def test_payment_api_failure(monkeypatch, verified_agent):
    def fake_call_llm(system, messages):
        return json.dumps({
            "amount": 100, "card_number": "4532015112830366", 
            "cvv": "123", "expiry_month": 12, "expiry_year": 2030, "cardholder_name": "Nithin"
        })
    def fake_process(account_id, amount, card):
        return {"success": False, "error_code": "card_declined"}

    monkeypatch.setattr(agent_module, "call_llm", fake_call_llm)
    monkeypatch.setattr(agent_module, "process_payment", fake_process)

    verified_agent.next("Pay")
    
    assert verified_agent.ctx.state == agent_module.OUTCOME
    assert verified_agent.ctx.payment_result["success"] is False
    assert verified_agent.ctx.payment_result["error_code"] == "card_declined"
