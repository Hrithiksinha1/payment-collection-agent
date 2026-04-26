from agent.agent import Agent
import sys

# ANSI escape for dim text
DIM = "\033[2m"
RESET = "\033[0m"


def _safe_console_text(text: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def print_banner():
    print("\n" + "=" * 60)
    print("Payment Collection Agent")
    print("=" * 60)
    print("Test Accounts:")
    print("  ACC1001 | Nithin Jain | Balance: Rs 1250.75")
    print("  ACC1002 | Rajarajeswari Balasubramaniam | Balance: Rs 540.00")
    print("  ACC1003 | Priya Agarwal | Balance: Rs 0.00")
    print("  ACC1004 | Rahul Mehta | Balance: Rs 3200.50")
    print("=" * 60)
    print("Type 'exit' or 'quit' to end.\n")


def main():
    agent = Agent()
    print_banner()

    try:
        while True:
            user_input = input("> ").strip()

            if user_input.lower() in ["exit", "quit"]:
                print("\nExiting. Goodbye!\n")
                break

            if not user_input:
                continue

            result = agent.next(user_input)

            print("\n" + _safe_console_text(result["message"]))

            # Print current state in dim text
            print(f"{DIM}[STATE: {agent.ctx.state}]{RESET}\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!\n")


if __name__ == "__main__":
    main()