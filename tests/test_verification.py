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
def agent():
    return Agent()

def test_verification_failure_wrong_name(monkeypatch, agent):
    # Mock lookup
    monkeypatch.setattr(agent_module, "lookup_account", lambda id: {
        "account_id": "ACC1001", "full_name": "Nithin Jain", "dob": "1990-05-14", "balance": 100
    })

    # Turn 1: Account ID
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"account_id": "ACC1001"}))
    agent.next("ACC1001")
    assert agent.ctx.state == agent_module.ACCOUNT_LOOKUP

    # Turn 2: Wrong Name -> Transition to VERIFICATION
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"name": "Wrong Name"}))
    agent.next("My name is Wrong Name")
    assert agent.ctx.state == agent_module.VERIFICATION

    # Turn 3: DOB -> Verification fails (because name is Wrong Name)
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"name": "Wrong Name", "dob": "1990-05-14"}))
    agent.next("My DOB is 1990-05-14")
    
    assert agent.ctx.verified is False
    assert agent.ctx.retry_count == 1
    assert agent.ctx.state == agent_module.VERIFICATION

def test_verification_retry_limit(monkeypatch, agent):
    monkeypatch.setattr(agent_module, "lookup_account", lambda id: {
        "account_id": "ACC1001", "full_name": "Good", "dob": "1990-01-01", "balance": 100
    })

    # Sequence to reach verification
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"account_id": "ACC1001"}))
    agent.next("ACC1001")
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"name": "Bad"}))
    agent.next("Bad Name")

    # Now we are in VERIFICATION. Fail it 3 times.
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"name": "Bad", "dob": "2000-01-01"}))
    agent.next("Attempt 1") # retry 1
    agent.next("Attempt 2") # retry 2
    agent.next("Attempt 3") # retry 3 -> RECAP
    
    assert agent.ctx.retry_count == 3
    assert agent.ctx.state == agent_module.RECAP
    
    agent.next("Goodbye")
    assert agent.ctx.state == TERMINATED

def test_verification_aadhaar_success(monkeypatch, agent):
    monkeypatch.setattr(agent_module, "lookup_account", lambda id: {
        "account_id": "ACC1001", "full_name": "Nithin Jain", "aadhaar_last4": "4321", "balance": 100
    })

    agent.ctx.account = {
        "account_id": "ACC1001", "full_name": "Nithin Jain", "aadhaar_last4": "4321", "balance": 100
    }
    agent.ctx.state = agent_module.VERIFICATION
    # Verification extracts name + aadhaar in this state
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"name": "Nithin Jain", "aadhaar": "4321"}))
    
    agent.next("Nithin Jain Aadhaar 4321")
    
    assert agent.ctx.verified is True
    assert agent.ctx.state == agent_module.PAYMENT_COLLECTION
