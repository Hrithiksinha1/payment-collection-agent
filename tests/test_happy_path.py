import pytest
import json
from pathlib import Path
import sys

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent.agent as agent_module
from agent.agent import Agent, TERMINATED

@pytest.fixture
def mock_dependencies(monkeypatch):
    """Mocks LLM, lookup, and payment for a successful flow."""
    
    def fake_call_llm(system, messages):
        if "data extractor" in system.lower():
            user_msg = messages[-1]["content"]
            # Flexible mock extraction
            data = {}
            if "ACC1001" in user_msg: data["account_id"] = "ACC1001"
            if "Nithin Jain" in user_msg: data["name"] = "Nithin Jain"
            if "1990-05-14" in user_msg: data["dob"] = "1990-05-14"
            if "500" in user_msg: data["amount"] = 500
            if "4532" in user_msg:
                data.update({
                    "card_number": "4532015112830366", "cvv": "123", 
                    "expiry_month": 12, "expiry_year": 2027, "cardholder_name": "Nithin Jain"
                })
            return json.dumps(data)
        return "Generic agent response."

    def fake_lookup(account_id):
        return {
            "account_id": "ACC1001", "full_name": "Nithin Jain", "balance": 1000,
            "dob": "1990-05-14", "aadhaar_last4": "4321", "pincode": "400001"
        }

    def fake_payment(account_id, amount, card):
        return {"success": True, "transaction_id": "txn_123"}

    monkeypatch.setattr(agent_module, "call_llm", fake_call_llm)
    monkeypatch.setattr(agent_module, "lookup_account", fake_lookup)
    monkeypatch.setattr(agent_module, "process_payment", fake_payment)

def test_full_happy_path(mock_dependencies):
    agent = Agent()
    
    # 1. GREETING -> ACCOUNT_LOOKUP
    agent.next("My account is ACC1001")
    assert agent.ctx.state == agent_module.ACCOUNT_LOOKUP
    
    # 2. ACCOUNT_LOOKUP -> VERIFICATION
    agent.next("I am Nithin Jain")
    assert agent.ctx.state == agent_module.VERIFICATION
    
    # 3. VERIFICATION (extracts dob) -> PAYMENT_COLLECTION
    agent.next("My DOB is 1990-05-14")
    assert agent.ctx.state == agent_module.PAYMENT_COLLECTION
    assert agent.ctx.verified is True
    
    # 4. PAYMENT_COLLECTION (extracts all) -> OUTCOME
    agent.next("Pay 500 with card 4532015112830366, CVV 123, exp 12/2027, name Nithin Jain")
    assert agent.ctx.state == agent_module.OUTCOME
    
    # 5. OUTCOME -> RECAP
    agent.next("No more questions")
    assert agent.ctx.state == agent_module.RECAP

    # 6. RECAP -> TERMINATED
    agent.next("Bye")
    assert agent.ctx.state == TERMINATED
