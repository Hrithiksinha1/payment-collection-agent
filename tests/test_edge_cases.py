import pytest
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent.agent as agent_module
from agent.agent import Agent, TERMINATED

def test_edge_case_leap_year(monkeypatch):
    agent = Agent()
    def fake_lookup(account_id):
        return {"account_id": "ACC1004", "full_name": "Rahul Mehta", "dob": "1988-02-29", "balance": 100}
    
    monkeypatch.setattr(agent_module, "lookup_account", fake_lookup)
    
    # Sequence to reach verification
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"account_id": "ACC1004"}))
    agent.next("ACC1004")
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"name": "Rahul Mehta"}))
    agent.next("Rahul Mehta")
    
    # Now verify with Leap Year DOB
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"name": "Rahul Mehta", "dob": "1988-02-29"}))
    agent.next("29 Feb 1988")
    
    assert agent.ctx.verified is True

def test_edge_case_terminated_rejection(monkeypatch):
    agent = Agent()
    agent.ctx.state = TERMINATED
    
    res = agent.next("Hello?")
    assert "ended" in res["message"].lower()

def test_edge_case_out_of_order_input(monkeypatch):
    """Test that agent ignores fields not relevant to current state."""
    agent = Agent()
    def fake_call_llm(system, messages):
        # Even if user gives name, GREETING state only extracts account_id
        return json.dumps({"account_id": "ACC1001", "name": "Nithin Jain"})
    
    monkeypatch.setattr(agent_module, "call_llm", fake_call_llm)
    monkeypatch.setattr(agent_module, "lookup_account", lambda id: {"balance": 0})

    agent.next("ACC1001, my name is Nithin")
    
    assert "account_id" in agent.ctx.collected
    assert "name" not in agent.ctx.collected # Should NOT have extracted name yet
    assert agent.ctx.state == agent_module.ACCOUNT_LOOKUP

def test_edge_case_account_not_found(monkeypatch):
    agent = Agent()
    def fake_lookup(id):
        raise agent_module.AccountNotFoundError("Not found")
    monkeypatch.setattr(agent_module, "lookup_account", fake_lookup)
    monkeypatch.setattr(agent_module, "call_llm", lambda s, m: json.dumps({"account_id": "ACC9999"}))

    agent.next("ACC9999")
    
    assert agent.ctx.state == "GREETING"
    assert "account_id" not in agent.ctx.collected
    assert agent.ctx.last_error is not None
    assert "no account found" in agent.ctx.last_error.lower()
