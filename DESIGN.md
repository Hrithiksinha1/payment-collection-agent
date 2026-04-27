# Design Document: Payment Collection AI Agent

## Architecture Overview

The agent is built using a **Deterministic State Machine + LLM Extraction** architecture. This design separates conversational intelligence from business logic, ensuring that the agent remains reliable, predictable, and secure.

### Core Components

1.  **State Machine (`agent/agent.py`)**:
    - Manages the conversation flow through predefined states: `GREETING`, `ACCOUNT_LOOKUP`, `VERIFICATION`, `PAYMENT_COLLECTION`, `OUTCOME`, and `TERMINATED`.
    - Business decisions (e.g., "Is the user verified?", "Is the balance sufficient?") are handled exclusively in Python logic, not by the LLM.

2.  **Field Extraction (`agent/agent.py`)**:
    - Uses a scoped LLM call each turn to extract specific JSON fields (e.g., `account_id`, `amount`) from user input.
    - The extraction is "state-aware"—it only looks for fields relevant to the current state, preventing the LLM from accidentally triggering state transitions with hallucinated data.

3.  **Dynamic Prompting (`agent/prompts.py`)**:
    - Generates system prompts based on the current state and the "Source of Truth" (`ctx.collected` data).
    - Instructs the LLM to strictly follow the state's goals and avoid assuming any data that hasn't been validated by the backend.

4.  **Validation Layer (`validators/`)**:
    - Decoupled modules for Identity, Card (Luhn, CVV, Expiry), and Amount validation.
    - These provide granular error messages that are passed back to the LLM to guide the user.

## Key Decisions & Rationale

### 1. Deterministic Flow Control over LLM Autonomy
- **Decision**: Used a hardcoded state machine instead of allowing the LLM to choose tools or transitions (e.g., via OpenAI Function Calling).
- **Rationale**: In payment collection, the sequence of steps (Lookup -> Verify -> Balance -> Pay) is non-negotiable. A state machine guarantees the agent never skips verification or leaks data before authorization.

### 2. Scoped LLM Extraction
- **Decision**: Extraction happens before state transition and is limited to state-specific keys.
- **Rationale**: Prevents "hallucinated progress" where an LLM might think it saw an account ID in a generic greeting, or where it might try to process a payment while still in the verification phase.

### 3. Strict Identity Matching
- **Decision**: Enforced exact string matching for names and strict equality for secondary factors.
- **Rationale**: Compliance and security requirements for financial transactions demand high precision. Fuzzy matching was avoided to prevent unauthorized access to account balances.

### 4. Leap Year Handling
- **Decision**: Relied on the LLM's natural language processing to standardize date formats (e.g., "Feb 29 1988" -> "1988-02-29") before passing them to the validator.
- **Rationale**: This leverages the LLM's strength in text normalization while keeping the actual "comparison" logic deterministic.

## Tradeoffs Accepted

- **Rigidity**: The agent follows a strict path. If a user tries to jump to the end immediately, the agent will politely pull them back to the current step. This is a tradeoff of "Conversational Fluidity" in favor of "Process Compliance."
- **Two LLM Calls per Turn**: One for extraction and one for response. This increases latency and cost but significantly improves extraction accuracy and state reliability.

## Future Improvements

- **Asynchronous Processing**: Parallelizing the LLM calls and API requests to reduce turn-around time.
- **Improved Recovery**: Adding "intent classification" to handle cases where users ask meta-questions (e.g., "Why do you need my Aadhaar?") without breaking the state flow.
- **Context Window Management**: Implementing a summary buffer for extremely long conversations to keep the LLM focused on the current task.
