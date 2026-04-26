from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent.agent as agent_module
from agent.agent import Agent


def test_extract_fields_uses_llm_only(monkeypatch):
    agent = Agent()
    called = {"count": 0}

    def fake_call_llm(system, messages):
        called["count"] += 1
        assert "data extractor" in system.lower()
        assert messages == [{"role": "user", "content": "my account is acc1001"}]
        return '{"account_id":"ACC1001"}'

    monkeypatch.setattr(agent_module, "call_llm", fake_call_llm)

    extracted = agent._extract_fields("my account is acc1001", ["account_id"])

    assert called["count"] == 1
    assert extracted == {"account_id": "ACC1001"}


def test_next_runs_extraction_llm_and_response_llm(monkeypatch):
    agent = Agent()
    llm_calls = {"extract": 0, "response": 0}

    def fake_call_llm(system, messages):
        if "data extractor" in system.lower():
            llm_calls["extract"] += 1
            return '{"account_id":"ACC1001"}'
        llm_calls["response"] += 1
        return "Please share your full name for verification."

    def fake_lookup_account(account_id):
        assert account_id == "ACC1001"
        return {
            "account_id": "ACC1001",
            "full_name": "Nithin Jain",
            "dob": "1990-05-14",
            "aadhaar_last4": "4321",
            "pincode": "400001",
            "balance": 1250.75,
        }

    monkeypatch.setattr(agent_module, "call_llm", fake_call_llm)
    monkeypatch.setattr(agent_module, "lookup_account", fake_lookup_account)

    result = agent.next("ACC1001")

    assert llm_calls["extract"] == 1
    assert llm_calls["response"] == 1
    assert agent.ctx.state == agent_module.ACCOUNT_LOOKUP
    assert result["message"] == "Please share your full name for verification."


def test_llm_extract_parses_json_wrapped_in_markdown(monkeypatch):
    agent = Agent()

    def fake_call_llm(system, messages):
        return """Here is the extracted data:
```json
{"amount": 5, "card_number": null}
```"""

    monkeypatch.setattr(agent_module, "call_llm", fake_call_llm)

    extracted = agent._llm_extract("I want to pay Rs 5", ["amount", "card_number"])

    assert extracted == {"amount": 5, "card_number": None}


def test_llm_extract_prompt_mentions_amount_variants(monkeypatch):
    agent = Agent()
    captured = {"system": None}

    def fake_call_llm(system, messages):
        captured["system"] = system
        return '{"amount": 5}'

    monkeypatch.setattr(agent_module, "call_llm", fake_call_llm)

    _ = agent._llm_extract("I want to pay 5 ruppess", ["amount"])

    assert "5 ruppess" in captured["system"]
