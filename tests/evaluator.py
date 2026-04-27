"""
evaluator.py -- Automated Evaluation Script for the Payment Collection Agent
============================================================================
Runs the agent through multiple scripted scenarios, checking:
  - Final agent state
  - Required keywords in agent responses
  - Correct tool calls (lookup + payment)
  - Retry and failure behaviour

Usage:
    python tests/evaluator.py           # run all scenarios and print report
    python tests/evaluator.py --verbose  # also print per-turn transcripts
"""

from pathlib import Path
import sys
import time
import json
import argparse
from dataclasses import dataclass, field
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent.agent as agent_module
from agent.agent import Agent, TERMINATED, OUTCOME


# ==================================================================
#  MOCK HELPERS
# ==================================================================

ACCOUNTS = {
    "ACC1001": {
        "account_id": "ACC1001",
        "full_name": "Nithin Jain",
        "dob": "1990-05-14",
        "aadhaar_last4": "4321",
        "pincode": "400001",
        "balance": 1250.75,
    },
    "ACC1002": {
        "account_id": "ACC1002",
        "full_name": "Rajarajeswari Balasubramaniam",
        "dob": "1985-11-23",
        "aadhaar_last4": "9876",
        "pincode": "400002",
        "balance": 540.00,
    },
    "ACC1003": {
        "account_id": "ACC1003",
        "full_name": "Priya Agarwal",
        "dob": "1992-08-10",
        "aadhaar_last4": "2468",
        "pincode": "400003",
        "balance": 0.00,
    },
    "ACC1004": {
        "account_id": "ACC1004",
        "full_name": "Rahul Mehta",
        "dob": "1988-02-29",
        "aadhaar_last4": "1357",
        "pincode": "400004",
        "balance": 3200.50,
    },
}

VALID_CARD = {
    "cardholder_name": "Nithin Jain",
    "card_number": "4532015112830366",
    "cvv": "123",
    "expiry_month": 12,
    "expiry_year": 2027,
}


def make_fake_lookup(call_log: list):
    """Returns a fake lookup_account that logs calls and raises on unknown IDs."""
    def fake_lookup(account_id: str) -> dict:
        call_log.append({"tool": "lookup_account", "account_id": account_id})
        if account_id not in ACCOUNTS:
            raise agent_module.AccountNotFoundError(f"No account found: {account_id}")
        return ACCOUNTS[account_id]
    return fake_lookup


def make_fake_process_payment(call_log: list, succeed: bool = True, error_code: str = "card_declined"):
    """Returns a fake process_payment that logs calls and returns success/failure."""
    def fake_process(account_id: str, amount: float, card: dict) -> dict:
        call_log.append({
            "tool": "process_payment",
            "account_id": account_id,
            "amount": amount,
            "card_last4": str(card.get("card_number", ""))[-4:],
        })
        if succeed:
            return {"success": True, "transaction_id": "txn_eval_test_001"}
        return {"success": False, "error_code": error_code}
    return fake_process


def make_fake_llm(extraction_map: dict | None = None):
    """
    Returns a fake call_llm.
    - Extraction calls (system contains 'data extractor') use extraction_map to
      return pre-scripted JSON based on the user message.
    - Response calls return a minimal but state-appropriate string.
    """
    def fake_call_llm(system: str, messages: list) -> str:
        is_extractor = "data extractor" in system.lower()
        if is_extractor:
            user_msg = messages[-1]["content"] if messages else ""
            if extraction_map and user_msg in extraction_map:
                return json.dumps(extraction_map[user_msg])
            # Fallback: return all-null JSON
            import re
            keys_match = re.search(r"Keys to extract:\s*(.+)", system)
            if keys_match:
                keys = [k.strip() for k in keys_match.group(1).split(",")]
                return json.dumps({k: None for k in keys})
            return "{}"
        # Response LLM -- return a generic placeholder
        if "GREETING" in system:
            return "Welcome! Please provide your account ID."
        if "ACCOUNT_LOOKUP" in system:
            return "Account found. Please provide your full name."
        if "VERIFICATION" in system:
            return "Please verify your identity with your name and DOB."
        if "PAYMENT_COLLECTION" in system:
            return "Please provide your card details to proceed."
        if "OUTCOME" in system:
            if "SUCCESS" in system:
                return "Payment successful! Transaction ID: txn_eval_test_001."
            return "Payment failed. Please check your card details."
        if "TERMINATED" in system:
            return "Thank you. Goodbye!"
        return "Understood. Please continue."
    return fake_call_llm


# ==================================================================
#  RESULT DATACLASS
# ==================================================================

@dataclass
class ScenarioResult:
    name: str
    passed: bool
    checks_total: int
    checks_passed: int
    failures: list[str] = field(default_factory=list)
    turns: int = 0
    duration_ms: float = 0.0
    transcript: list[dict] = field(default_factory=list)


# ==================================================================
#  SCENARIO RUNNER
# ==================================================================

class ScenarioRunner:
    """
    Runs a scripted scenario against the Agent.

    Args:
        name:           Human-readable scenario name.
        turns:          List of (user_input, extraction_result) pairs.
                        extraction_result is a dict keyed by user_input; the value
                        is the JSON dict the fake LLM extractor returns for that turn.
        checks:         List of (description, callable(agent, tool_log) -> bool) pairs.
        lookup_succeed: Whether the fake lookup should find the account.
        payment_succeed: Whether the fake payment should succeed.
        payment_error:  Error code returned on payment failure.
    """

    def __init__(
        self,
        name: str,
        turns: list[tuple[str, dict]],
        checks: list[tuple[str, Callable]],
        lookup_succeed: bool = True,
        payment_succeed: bool = True,
        payment_error: str = "card_declined",
    ):
        self.name = name
        self.turns = turns
        self.checks = checks
        self.lookup_succeed = lookup_succeed
        self.payment_succeed = payment_succeed
        self.payment_error = payment_error

    def run(self, verbose: bool = False) -> ScenarioResult:
        tool_log: list[dict] = []
        transcript: list[dict] = []

        # Build extraction_map: user_input -> extracted JSON dict
        extraction_map = {}
        for user_input, extracted in self.turns:
            extraction_map[user_input] = extracted

        # Patch agent module with fakes
        original_lookup = agent_module.lookup_account
        original_payment = agent_module.process_payment
        original_llm = agent_module.call_llm

        agent_module.lookup_account = make_fake_lookup(tool_log)
        agent_module.process_payment = make_fake_process_payment(
            tool_log, succeed=self.payment_succeed, error_code=self.payment_error
        )
        agent_module.call_llm = make_fake_llm(extraction_map)

        start = time.monotonic()
        ag = Agent()
        num_turns = 0

        try:
            for user_input, _ in self.turns:
                result = ag.next(user_input)
                num_turns += 1
                transcript.append({"user": user_input, "agent": result.get("message", "")})
                if verbose:
                    print(f"    [turn {num_turns}] user: {user_input!r}")
                    print(f"    [turn {num_turns}] agent: {result.get('message','')[:120]!r}")
                    print(f"    [turn {num_turns}] state: {ag.ctx.state}")
        finally:
            agent_module.lookup_account = original_lookup
            agent_module.process_payment = original_payment
            agent_module.call_llm = original_llm

        duration_ms = (time.monotonic() - start) * 1000

        # Evaluate checks
        checks_passed = 0
        failures = []
        for desc, check_fn in self.checks:
            try:
                ok = check_fn(ag, tool_log)
            except Exception as exc:
                ok = False
                desc = f"{desc} [EXCEPTION: {exc}]"
            if ok:
                checks_passed += 1
            else:
                failures.append(desc)

        passed = checks_passed == len(self.checks)
        return ScenarioResult(
            name=self.name,
            passed=passed,
            checks_total=len(self.checks),
            checks_passed=checks_passed,
            failures=failures,
            turns=num_turns,
            duration_ms=duration_ms,
            transcript=transcript,
        )


# ==================================================================
#  SCENARIO DEFINITIONS
# ==================================================================

def build_scenarios() -> list[ScenarioRunner]:
    scenarios = []

    # -- 1. Happy Path -- full successful payment -----------------
    scenarios.append(ScenarioRunner(
        name="Happy Path: Successful End-to-End Payment (ACC1001)",
        turns=[
            ("Hi",           {"account_id": None}),
            ("ACC1001",      {"account_id": "ACC1001"}),
            ("Nithin Jain",  {"name": "Nithin Jain"}),
            ("DOB is 1990-05-14", {"dob": "1990-05-14", "name": "Nithin Jain", "aadhaar": None, "pincode": None}),
            ("500",          {"amount": 500}),
            ("4532015112830366 CVV 123 expiry 12/2027 cardholder Nithin Jain",
             {"card_number": "4532015112830366", "cvv": "123",
              "expiry_month": 12, "expiry_year": 2027, "cardholder_name": "Nithin Jain"}),
            ("Thank you, bye!", {}),
            ("...", {}),
        ],
        checks=[
            ("Agent reaches TERMINATED state",
             lambda ag, log: ag.ctx.state == TERMINATED),
            ("lookup_account was called once",
             lambda ag, log: sum(1 for e in log if e["tool"] == "lookup_account") == 1),
            ("lookup_account used ACC1001",
             lambda ag, log: any(e["tool"] == "lookup_account" and e["account_id"] == "ACC1001" for e in log)),
            ("process_payment was called once",
             lambda ag, log: sum(1 for e in log if e["tool"] == "process_payment") == 1),
            ("process_payment amount is 500",
             lambda ag, log: any(e["tool"] == "process_payment" and e["amount"] == 500.0 for e in log)),
            ("payment_result success is True",
             lambda ag, log: ag.ctx.payment_result is not None and ag.ctx.payment_result.get("success") is True),
            ("transaction_id is present",
             lambda ag, log: ag.ctx.payment_result is not None and "txn_eval_test_001" in ag.ctx.payment_result.get("transaction_id", "")),
        ],
    ))

    # -- 2. Verification Failure -- user exhausts all 3 retries --
    bad_verify = {"dob": "1999-01-01", "name": "Wrong Name", "aadhaar": None, "pincode": None}
    scenarios.append(ScenarioRunner(
        name="Verification Failure: Exhausts 3 Retries -> TERMINATED",
        turns=[
            ("Hi",              {"account_id": None}),
            ("ACC1001",         {"account_id": "ACC1001"}),
            ("Wrong Name",      {"name": "Wrong Name"}),
            ("DOB 1999-01-01",  bad_verify),   # retry 1
            ("Wrong Name",      {"name": "Wrong Name"}),
            ("DOB 1999-01-01",  bad_verify),   # retry 2
            ("Wrong Name",      {"name": "Wrong Name"}),
            ("DOB 1999-01-01",  bad_verify),   # retry 3 -> RECAP
            ("Goodbye",         {}),           # hits TERMINATED
        ],
        checks=[
            ("Agent reaches TERMINATED state after 3 failed retries",
             lambda ag, log: ag.ctx.state == TERMINATED),
            ("retry_count reached 3",
             lambda ag, log: ag.ctx.retry_count >= 3),
            ("process_payment was NEVER called",
             lambda ag, log: not any(e["tool"] == "process_payment" for e in log)),
            ("agent is not verified",
             lambda ag, log: ag.ctx.verified is False),
        ],
    ))

    # -- 3. Payment Failure -- API returns 422 insufficient_balance
    scenarios.append(ScenarioRunner(
        name="Payment Failure: API Returns insufficient_balance",
        turns=[
            ("Hi",           {"account_id": None}),
            ("ACC1001",      {"account_id": "ACC1001"}),
            ("Nithin Jain",  {"name": "Nithin Jain"}),
            ("DOB is 1990-05-14", {"dob": "1990-05-14", "name": "Nithin Jain", "aadhaar": None, "pincode": None}),
            ("999999",       {"amount": 999999}),  # passes validator (balance 1250.75) only if <= balance
            ("4532015112830366 CVV 123 expiry 12/2027 cardholder Nithin Jain",
             {"card_number": "4532015112830366", "cvv": "123",
              "expiry_month": 12, "expiry_year": 2027, "cardholder_name": "Nithin Jain"}),
        ],
        checks=[
            ("Agent does not reach OUTCOME state due to validation block",
             lambda ag, log: ag.ctx.state != TERMINATED or ag.ctx.payment_result is None
                             or ag.ctx.payment_result.get("success") is not True),
            ("process_payment was NOT called (amount exceeds balance, caught by validator)",
             lambda ag, log: not any(e["tool"] == "process_payment" for e in log)),
        ],
    ))

    # -- 4. Payment Failure -- API-level card_declined (validator passes) -
    scenarios.append(ScenarioRunner(
        name="Payment Failure: API Returns card_declined Error",
        turns=[
            ("Hi",           {"account_id": None}),
            ("ACC1001",      {"account_id": "ACC1001"}),
            ("Nithin Jain",  {"name": "Nithin Jain"}),
            ("DOB is 1990-05-14", {"dob": "1990-05-14", "name": "Nithin Jain", "aadhaar": None, "pincode": None}),
            ("500",          {"amount": 500}),
            ("4532015112830366 CVV 123 expiry 12/2027 cardholder Nithin Jain",
             {"card_number": "4532015112830366", "cvv": "123",
              "expiry_month": 12, "expiry_year": 2027, "cardholder_name": "Nithin Jain"}),
            ("Okay, goodbye.", {}),
            ("...", {}),
        ],
        payment_succeed=False,
        payment_error="card_declined",
        checks=[
            ("process_payment was called once",
             lambda ag, log: sum(1 for e in log if e["tool"] == "process_payment") == 1),
            ("payment_result success is False",
             lambda ag, log: ag.ctx.payment_result is not None and ag.ctx.payment_result.get("success") is False),
            ("payment_result contains error_code",
             lambda ag, log: ag.ctx.payment_result is not None and "error_code" in ag.ctx.payment_result),
            ("Agent reaches TERMINATED after showing failure outcome",
             lambda ag, log: ag.ctx.state == TERMINATED),
        ],
    ))

    # -- 5. Unknown Account ID -----------------------------------
    scenarios.append(ScenarioRunner(
        name="Edge Case: Unknown Account ID (ACC9999)",
        turns=[
            ("Hi",      {"account_id": None}),
            ("ACC9999", {"account_id": "ACC9999"}),
        ],
        checks=[
            ("Agent stays in GREETING state after unknown account",
             lambda ag, log: ag.ctx.state == "GREETING"),
            ("lookup_account was called once",
             lambda ag, log: sum(1 for e in log if e["tool"] == "lookup_account") == 1),
            ("account_id cleared from collected after failure",
             lambda ag, log: "account_id" not in ag.ctx.collected),
        ],
    ))

    # -- 6. Zero-Balance Account (ACC1003) -----------------------
    scenarios.append(ScenarioRunner(
        name="Edge Case: Zero-Balance Account (ACC1003) -- Payment Blocked by Validator",
        turns=[
            ("Hi",            {"account_id": None}),
            ("ACC1003",       {"account_id": "ACC1003"}),
            ("Priya Agarwal", {"name": "Priya Agarwal"}),
            ("DOB is 1992-08-10", {"dob": "1992-08-10", "name": "Priya Agarwal", "aadhaar": None, "pincode": None}),
            ("100",           {"amount": 100}),
            ("4532015112830366 CVV 123 expiry 12/2027 cardholder Priya Agarwal",
             {"card_number": "4532015112830366", "cvv": "123",
              "expiry_month": 12, "expiry_year": 2027, "cardholder_name": "Priya Agarwal"}),
        ],
        checks=[
            ("process_payment was NEVER called for zero-balance account",
             lambda ag, log: not any(e["tool"] == "process_payment" for e in log)),
            ("User was verified successfully",
             lambda ag, log: ag.ctx.verified is True),
        ],
    ))

    # -- 7. Partial Payment -------------------------------------
    scenarios.append(ScenarioRunner(
        name="Partial Payment: Amount Less Than Balance (ACC1004)",
        turns=[
            ("Hi",           {"account_id": None}),
            ("ACC1004",      {"account_id": "ACC1004"}),
            ("Rahul Mehta",  {"name": "Rahul Mehta"}),
            ("DOB is 1988-02-29", {"dob": "1988-02-29", "name": "Rahul Mehta", "aadhaar": None, "pincode": None}),
            ("100",          {"amount": 100}),
            ("4532015112830366 CVV 123 expiry 12/2027 cardholder Rahul Mehta",
             {"card_number": "4532015112830366", "cvv": "123",
              "expiry_month": 12, "expiry_year": 2027, "cardholder_name": "Rahul Mehta"}),
            ("Thanks!", {}),
            ("...", {}),
        ],
        checks=[
            ("process_payment called with partial amount 100",
             lambda ag, log: any(e["tool"] == "process_payment" and e["amount"] == 100.0 for e in log)),
            ("payment_result success is True",
             lambda ag, log: ag.ctx.payment_result is not None and ag.ctx.payment_result.get("success") is True),
            ("Agent reaches TERMINATED",
             lambda ag, log: ag.ctx.state == TERMINATED),
        ],
    ))

    # -- 8. Aadhaar-based verification --------------------------
    scenarios.append(ScenarioRunner(
        name="Verification via Aadhaar Last 4 Digits (ACC1002)",
        turns=[
            ("Hi",                         {"account_id": None}),
            ("ACC1002",                    {"account_id": "ACC1002"}),
            ("Rajarajeswari Balasubramaniam", {"name": "Rajarajeswari Balasubramaniam"}),
            ("Aadhaar last 4 is 9876",
             {"aadhaar": "9876", "name": "Rajarajeswari Balasubramaniam", "dob": None, "pincode": None}),
        ],
        checks=[
            ("User verified via Aadhaar factor",
             lambda ag, log: ag.ctx.verified is True),
            ("Agent moves to PAYMENT_COLLECTION",
             lambda ag, log: ag.ctx.state in ("PAYMENT_COLLECTION", TERMINATED)),
        ],
    ))

    # -- 9. Pincode-based verification --------------------------
    scenarios.append(ScenarioRunner(
        name="Verification via Pincode (ACC1001)",
        turns=[
            ("Hi",           {"account_id": None}),
            ("ACC1001",      {"account_id": "ACC1001"}),
            ("Nithin Jain",  {"name": "Nithin Jain"}),
            ("Pincode is 400001", {"pincode": "400001", "name": "Nithin Jain", "dob": None, "aadhaar": None}),
        ],
        checks=[
            ("User verified via Pincode factor",
             lambda ag, log: ag.ctx.verified is True),
            ("Agent moves to PAYMENT_COLLECTION",
             lambda ag, log: ag.ctx.state in ("PAYMENT_COLLECTION", TERMINATED)),
        ],
    ))

    # -- 10. Terminated conversation rejects further input ------
    scenarios.append(ScenarioRunner(
        name="Edge Case: Further Input After TERMINATED Returns Session-Ended Message",
        turns=[
            ("Hi",           {"account_id": None}),
            ("ACC1001",      {"account_id": "ACC1001"}),
            ("Nithin Jain",  {"name": "Nithin Jain"}),
            ("DOB is 1990-05-14", {"dob": "1990-05-14", "name": "Nithin Jain", "aadhaar": None, "pincode": None}),
            ("500",          {"amount": 500}),
            ("4532015112830366 CVV 123 expiry 12/2027 cardholder Nithin Jain",
             {"card_number": "4532015112830366", "cvv": "123",
              "expiry_month": 12, "expiry_year": 2027, "cardholder_name": "Nithin Jain"}),
            ("I want to pay again", {}),   # hits RECAP
            ("Are you there?", {}),        # hits TERMINATED
            ("One more thing", {}),        # stays TERMINATED
        ],
        checks=[
            ("Agent stays TERMINATED after post-termination input",
             lambda ag, log: ag.ctx.state == TERMINATED),
            ("process_payment called exactly once (not twice)",
             lambda ag, log: sum(1 for e in log if e["tool"] == "process_payment") == 1),
        ],
    ))

    # -- 11. Leap Year Edge Case (ACC1004 - DOB 1988-02-29) -----
    scenarios.append(ScenarioRunner(
        name="Edge Case: Leap Year DOB Exact Match (ACC1004)",
        turns=[
            ("Hi",              {"account_id": None}),
            ("ACC1004",         {"account_id": "ACC1004"}),
            ("Rahul Mehta",     {"name": "Rahul Mehta"}),
            ("DOB 1988-02-29",  {"dob": "1988-02-29", "name": "Rahul Mehta", "aadhaar": None, "pincode": None}),
        ],
        checks=[
            ("User with leap year DOB is verified successfully",
             lambda ag, log: ag.ctx.verified is True),
        ],
    ))

    # -- 12. Wrong case name rejection --------------------------
    scenarios.append(ScenarioRunner(
        name="Verification Failure: Wrong Name Case (nithin jain vs Nithin Jain)",
        turns=[
            ("Hi",           {"account_id": None}),
            ("ACC1001",      {"account_id": "ACC1001"}),
            ("nithin jain",  {"name": "nithin jain"}),
            ("DOB 1990-05-14", {"dob": "1990-05-14", "name": "nithin jain", "aadhaar": None, "pincode": None}),
        ],
        checks=[
            ("Verification rejected for wrong-case name",
             lambda ag, log: ag.ctx.verified is False),
            ("retry_count incremented",
             lambda ag, log: ag.ctx.retry_count >= 1),
        ],
    ))

    return scenarios


# ==================================================================
#  METRICS CALCULATION
# ==================================================================

def compute_metrics(results: list[ScenarioResult]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    total_checks = sum(r.checks_total for r in results)
    passed_checks = sum(r.checks_passed for r in results)
    avg_turns = sum(r.turns for r in results) / total if total else 0
    avg_duration = sum(r.duration_ms for r in results) / total if total else 0

    return {
        "total_scenarios": total,
        "scenarios_passed": passed,
        "scenarios_failed": total - passed,
        "scenario_pass_rate": f"{passed / total * 100:.1f}%" if total else "N/A",
        "total_checks": total_checks,
        "checks_passed": passed_checks,
        "checks_failed": total_checks - passed_checks,
        "check_pass_rate": f"{passed_checks / total_checks * 100:.1f}%" if total_checks else "N/A",
        "avg_turns_per_scenario": round(avg_turns, 1),
        "avg_duration_ms": round(avg_duration, 1),
    }


# ==================================================================
#  REPORT PRINTER
# ==================================================================

SEP = "=" * 70


def print_report(results: list[ScenarioResult], metrics: dict, verbose: bool = False) -> None:
    print(f"\n{SEP}")
    print("  PAYMENT AGENT -- EVALUATION REPORT")
    print(SEP)

    for i, r in enumerate(results, 1):
        status = "[PASS]" if r.passed else "[FAIL]"
        print(f"\n[{i:02d}] {status}  {r.name}")
        print(f"      Checks: {r.checks_passed}/{r.checks_total} passed  |  "
              f"Turns: {r.turns}  |  Duration: {r.duration_ms:.0f}ms")
        if not r.passed:
            for f in r.failures:
                print(f"      X FAILED CHECK: {f}")
        if verbose and r.transcript:
            print("      -- Transcript --")
            for turn in r.transcript:
                print(f"        USER : {turn['user']}")
                print(f"        AGENT: {turn['agent'][:120]}")

    print(f"\n{SEP}")
    print("  METRICS SUMMARY")
    print(SEP)
    for key, val in metrics.items():
        label = key.replace("_", " ").title()
        print(f"  {label:<35} {val}")
    print(SEP + "\n")


# ==================================================================
#  MAIN
# ==================================================================

def main():
    parser = argparse.ArgumentParser(description="Run payment agent evaluation scenarios.")
    parser.add_argument("--verbose", action="store_true", help="Print per-turn transcripts.")
    args = parser.parse_args()

    scenarios = build_scenarios()
    results = []

    print(f"\nRunning {len(scenarios)} evaluation scenarios...")
    for scenario in scenarios:
        result = scenario.run(verbose=args.verbose)
        results.append(result)
        marker = "[PASS]" if result.passed else "[FAIL]"
        print(f"  {marker} {result.name}")

    metrics = compute_metrics(results)
    print_report(results, metrics, verbose=args.verbose)

    # Exit with non-zero code if any scenario failed (useful in CI)
    failed = sum(1 for r in results if not r.passed)
    sys.exit(failed)


if __name__ == "__main__":
    main()
