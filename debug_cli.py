import os
import sys
from pprint import pformat

import agent.agent as agent_module
from agent.agent import Agent
from agent.llm import call_llm as base_call_llm
from tools.lookup import lookup_account as base_lookup_account
from tools.payment import process_payment as base_process_payment
from validators.identity import verify_identity as base_verify_identity


DIM = "\033[2m"
RESET = "\033[0m"
TRACE = "[TRACE]"


def _safe_console_text(text: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def _is_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _debug_breakpoint(label: str) -> None:
    """Drop into debugger when DEBUG_BREAKPOINTS is enabled."""
    if _is_truthy(os.getenv("DEBUG_BREAKPOINTS", "0")):
        print(f"{TRACE} Breakpoint hit: {label}")
        breakpoint()


def install_trace_wrappers() -> None:
    """Monkeypatch runtime call points so processing is visible."""

    def traced_call_llm(system: str, messages: list) -> str:
        kind = "EXTRACTION" if "data extractor" in system.lower() else "RESPONSE"
        print(f"\n{TRACE} LLM CALL START [{kind}]")
        print(f"{TRACE} Messages count: {len(messages)}")
        print(f"{TRACE} Last message: {messages[-1] if messages else None}")
        _debug_breakpoint(f"before_llm_{kind.lower()}")
        response = base_call_llm(system, messages)
        print(f"{TRACE} LLM CALL END   [{kind}]")
        print(f"{TRACE} LLM response preview: {response[:180]!r}")
        _debug_breakpoint(f"after_llm_{kind.lower()}")
        return response

    def traced_lookup_account(account_id: str) -> dict:
        print(f"{TRACE} lookup_account(account_id={account_id!r})")
        _debug_breakpoint("before_lookup_account")
        result = base_lookup_account(account_id)
        print(f"{TRACE} lookup_account result keys: {list(result.keys())}")
        _debug_breakpoint("after_lookup_account")
        return result

    def traced_verify_identity(account, provided_name, factor, factor_value):
        print(
            f"{TRACE} verify_identity(name={provided_name!r}, "
            f"factor={factor!r}, value={factor_value!r})"
        )
        _debug_breakpoint("before_verify_identity")
        result = base_verify_identity(account, provided_name, factor, factor_value)
        print(f"{TRACE} verify_identity result: {result}")
        _debug_breakpoint("after_verify_identity")
        return result

    def traced_process_payment(account_id: str, amount: float, card: dict) -> dict:
        print(
            f"{TRACE} process_payment(account_id={account_id!r}, amount={amount!r}, "
            f"cardholder={card.get('cardholder_name')!r})"
        )
        _debug_breakpoint("before_process_payment")
        result = base_process_payment(account_id, amount, card)
        print(f"{TRACE} process_payment result: {result}")
        _debug_breakpoint("after_process_payment")
        return result

    # Patch symbols used inside agent.agent module
    agent_module.call_llm = traced_call_llm
    agent_module.lookup_account = traced_lookup_account
    agent_module.verify_identity = traced_verify_identity
    agent_module.process_payment = traced_process_payment


def print_banner() -> None:
    print("\n" + "=" * 70)
    print("Payment Collection Agent - Debug CLI")
    print("=" * 70)
    print("Type 'exit' or 'quit' to end.")
    print("Env toggles:")
    print("  DEBUG_BREAKPOINTS=1   -> enables Python breakpoints")
    print("=" * 70 + "\n")


def print_turn_snapshot(agent: Agent, when: str) -> None:
    ctx = agent.ctx
    print(f"{DIM}{TRACE} SNAPSHOT ({when}){RESET}")
    print(f"{DIM}{TRACE} state={ctx.state}{RESET}")
    print(f"{DIM}{TRACE} verified={ctx.verified} retry_count={ctx.retry_count}{RESET}")
    print(f"{DIM}{TRACE} collected={pformat(ctx.collected)}{RESET}")
    print(f"{DIM}{TRACE} last_error={ctx.last_error!r}{RESET}")
    print(f"{DIM}{TRACE} payment_result={pformat(ctx.payment_result)}{RESET}")
    print(f"{DIM}{TRACE} conversation_len={len(ctx.conversation)}{RESET}\n")


def main() -> None:
    install_trace_wrappers()
    agent = Agent()
    print_banner()

    try:
        while True:
            user_input = input("> ").strip()
            if user_input.lower() in {"exit", "quit"}:
                print("\nExiting debug session. Goodbye!\n")
                break
            if not user_input:
                continue

            print_turn_snapshot(agent, "BEFORE agent.next")
            _debug_breakpoint("before_agent_next")
            result = agent.next(user_input)
            _debug_breakpoint("after_agent_next")
            print_turn_snapshot(agent, "AFTER agent.next")

            print(_safe_console_text(result["message"]))
            print(f"{DIM}[STATE: {agent.ctx.state}]{RESET}\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!\n")


if __name__ == "__main__":
    main()
