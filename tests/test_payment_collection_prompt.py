from pathlib import Path
import sys
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.prompts import build_system_prompt


def test_payment_collection_prompt_lists_missing_amount():
    context = SimpleNamespace(
        collected={
            "account_id": "ACC1001",
            "card_number": "4532015112830366",
            "cvv": "123",
            "expiry_month": 12,
            "expiry_year": 2027,
            "cardholder_name": "Nithin Jain",
        },
        account={"balance": 1250.75},
        last_error=None,
    )

    prompt = build_system_prompt("PAYMENT_COLLECTION", context)

    assert "Ask the user ONLY for these missing fields: amount" in prompt
    assert "Do NOT say 'complete', 'processing', 'thank you for all details'" in prompt
