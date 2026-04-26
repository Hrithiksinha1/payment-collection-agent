import json
import logging
from typing import Dict, Any, Optional
from tools.lookup import lookup_account, AccountNotFoundError, ToolError
from tools.payment import process_payment
from .prompts import build_system_prompt
from validators.identity import verify_identity
from validators.card import luhn_check, validate_cvv, validate_expiry
from validators.amount import validate_amount
from .llm import call_llm

LOGGER = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#  STATES  (single source of truth — change here, changes everywhere)
# ════════════════════════════════════════════════════════════════
GREETING            = "GREETING"           # waiting for account ID
ACCOUNT_LOOKUP      = "ACCOUNT_LOOKUP"     # account found, waiting for full name
VERIFICATION        = "VERIFICATION"       # waiting for secondary factor
PAYMENT_COLLECTION  = "PAYMENT_COLLECTION" # collecting amount + card details
OUTCOME             = "OUTCOME"            # payment processed, show result
TERMINATED          = "TERMINATED"         # conversation over


# Fields the extraction LLM should look for per state
# This prevents hallucinated fields from silently skipping states
STATE_FIELDS = {
    GREETING:           ["account_id"],
    ACCOUNT_LOOKUP:     ["name"],
    VERIFICATION:       ["dob", "aadhaar", "pincode"],
    PAYMENT_COLLECTION: ["amount", "card_number", "cvv",
                         "expiry_month", "expiry_year", "cardholder_name"],
    OUTCOME:            [],
    TERMINATED:         [],
}


# ════════════════════════════════════════════════════════════════
#  CONTEXT  — all conversation state lives here
# ════════════════════════════════════════════════════════════════
class AgentContext:
    def __init__(self):
        self.state          = GREETING
        self.conversation   = []    # full message history sent to LLM each turn
        self.collected      = {}    # structured fields extracted from user input
        self.account        = None  # account data from lookup API (never exposed to user)
        self.verified       = False
        self.retry_count    = 0
        self.payment_result = None  # set after process_payment call
        self.last_error     = None  # tracks what went wrong for LLM to explain clearly


# ════════════════════════════════════════════════════════════════
#  AGENT
# ════════════════════════════════════════════════════════════════
class Agent:

    def __init__(self):
        self.ctx = AgentContext()

    # ── PUBLIC INTERFACE ────────────────────────────────────────
    def next(self, user_input: str) -> Dict[str, str]:
        ctx = self.ctx

        # Bail immediately if conversation is already over
        if ctx.state == TERMINATED:
            return {"message": "This conversation has ended. Please start a new session."}

        # 1. Add user message to history
        ctx.conversation.append({"role": "user", "content": user_input})

        # 2. Extract only fields relevant to the current state
        #    (prevents hallucinated fields from silently advancing states)
        extracted = self._extract_fields(user_input, STATE_FIELDS[ctx.state])
        for key, value in extracted.items():
            if value is not None and value != "":
                ctx.collected[key] = value

        # 3. Run state machine — pure Python decisions, no LLM involved
        ctx.last_error = None  # reset error each turn
        self._run_state_machine(ctx)

        # 4. Build state-specific system prompt and call LLM
        system_prompt = build_system_prompt(ctx.state, ctx)
        response      = call_llm(system_prompt, ctx.conversation)

        # 5. Add assistant response to history and return
        ctx.conversation.append({"role": "assistant", "content": response})
        return {"message": response}

    # ── STATE MACHINE ───────────────────────────────────────────
    def _run_state_machine(self, ctx: AgentContext) -> None:
        """
        All state transitions happen here.
        Each block handles exactly one state.
        Transitions only happen when ALL required data is present and valid.
        """

        # ── GREETING: wait for account ID, then look it up ──────
        if ctx.state == GREETING:
            account_id = ctx.collected.get("account_id")
            if not account_id:
                return  # nothing to do yet — LLM will ask for account ID

            try:
                ctx.account = lookup_account(account_id)
                ctx.state   = ACCOUNT_LOOKUP
                # Fall through to ACCOUNT_LOOKUP block immediately
                # so if name was already given, we don't wait an extra turn

            except AccountNotFoundError:
                ctx.last_error = f"No account found for '{account_id}'. Please check and try again."
                ctx.collected.pop("account_id", None)  # clear so user must re-enter
                return

            except ToolError as e:
                ctx.last_error = "We couldn't reach our servers. Please try again in a moment."
                return

        # ── ACCOUNT_LOOKUP: wait for full name ──────────────────
        if ctx.state == ACCOUNT_LOOKUP:
            name = ctx.collected.get("name")
            if not name:
                return  # LLM will ask for full name

            # Name collected — move to verification to check secondary factor
            ctx.state = VERIFICATION
            # Fall through immediately in case secondary factor was also given

        # ── VERIFICATION: check name + secondary factor ─────────
        if ctx.state == VERIFICATION:
            name   = ctx.collected.get("name")
            dob    = ctx.collected.get("dob")
            aadhaar = ctx.collected.get("aadhaar")
            pincode = ctx.collected.get("pincode")

            if not name:
                # Shouldn't happen (came from ACCOUNT_LOOKUP) but guard anyway
                return

            if not (dob or aadhaar or pincode):
                return  # LLM will ask for a secondary factor

            # Pick the first available secondary factor
            if dob:
                factor, factor_value = "dob", dob
            elif aadhaar:
                factor, factor_value = "aadhaar", aadhaar
            else:
                factor, factor_value = "pincode", pincode

            is_valid, reason = verify_identity(ctx.account, name, factor, factor_value)

            if is_valid:
                ctx.verified = True
                ctx.state    = PAYMENT_COLLECTION
                # Clear verification fields — no longer needed
                for key in ["name", "dob", "aadhaar", "pincode"]:
                    ctx.collected.pop(key, None)

            else:
                ctx.retry_count += 1
                ctx.last_error   = reason  # tells LLM what failed (without exposing account data)

                # Clear so user must re-enter cleanly
                for key in ["name", "dob", "aadhaar", "pincode"]:
                    ctx.collected.pop(key, None)

                if ctx.retry_count >= 3:
                    ctx.state = TERMINATED

        # ── PAYMENT COLLECTION: validate then charge ─────────────
        if ctx.state == PAYMENT_COLLECTION:
            required = ["amount", "card_number", "cvv",
                        "expiry_month", "expiry_year", "cardholder_name"]

            missing_fields = [field for field in required if field not in ctx.collected]
            if missing_fields:
                ctx.last_error = f"Missing payment details: {', '.join(missing_fields)}."
                return  # LLM will collect missing fields one by one

            amount        = self._safe_float(ctx.collected["amount"])
            card_number   = str(ctx.collected["card_number"]).replace(" ", "")
            cvv           = str(ctx.collected["cvv"])
            expiry_month  = self._safe_int(ctx.collected["expiry_month"])
            expiry_year   = self._safe_int(ctx.collected["expiry_year"])
            cardholder    = ctx.collected["cardholder_name"]

            # Run all validators and collect specific error messages
            errors = []

            valid_amount, amount_err   = validate_amount(amount, ctx.account["balance"])
            valid_card                 = luhn_check(card_number)
            valid_cvv, cvv_err         = validate_cvv(cvv, card_number)
            valid_expiry, expiry_err   = validate_expiry(expiry_month, expiry_year)

            if not valid_amount:  errors.append(amount_err)
            if not valid_card:    errors.append("Card number is invalid. Please re-enter your card number.")
            if not valid_cvv:     errors.append(cvv_err)
            if not valid_expiry:  errors.append(expiry_err)

            if errors:
                # Tell the LLM exactly what failed so it can explain clearly
                ctx.last_error = " | ".join(errors)
                # Only clear the fields that actually failed
                if not valid_amount:                        ctx.collected.pop("amount", None)
                if not valid_card:                          ctx.collected.pop("card_number", None)
                if not valid_cvv:                           ctx.collected.pop("cvv", None)
                if not valid_expiry:
                    ctx.collected.pop("expiry_month", None)
                    ctx.collected.pop("expiry_year", None)
                return

            # All validators passed — call payment API
            try:
                result = process_payment(
                    account_id = ctx.account["account_id"],
                    amount     = amount,
                    card       = {
                        "cardholder_name": cardholder,
                        "card_number":     card_number,
                        "cvv":             cvv,
                        "expiry_month":    expiry_month,
                        "expiry_year":     expiry_year,
                    }
                )
                ctx.payment_result = result
                ctx.state          = OUTCOME

            except ToolError:
                ctx.last_error = "Payment could not be processed due to a server error. Please try again."

        # ── OUTCOME: result has been set — LLM will communicate it ─
        # We do NOT move to TERMINATED here.
        # The LLM needs one full turn to show the transaction ID / error.
        # TERMINATED is set on the NEXT call after OUTCOME is shown.
        if ctx.state == OUTCOME:
            # Move to terminated AFTER this turn's LLM response is shown
            # We set a flag so next call to next() terminates gracefully
            pass  # state stays OUTCOME — _finalize_outcome handles it

    # ── HELPERS ─────────────────────────────────────────────────
    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            return float(str(value).replace(",", ""))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            return int(str(value).strip())
        except (ValueError, TypeError):
            return None

    # ── FIELD EXTRACTION ────────────────────────────────────────
    def _extract_fields(self, user_input: str, keys: list) -> Dict[str, Any]:
        """
        LLM-only extraction.

        Only extracts fields relevant to current state (keys param).
        This prevents hallucinated fields from silently skipping states.
        """
        if not keys:
            return {}

        return self._llm_extract(user_input, keys)

    def _llm_extract(self, user_input: str, keys: list) -> Dict[str, Any]:
        """Single-purpose LLM call that returns JSON only."""
        keys_str = ", ".join(keys)

        system = f"""You are a data extractor. Extract fields from user input and return ONLY valid JSON.

Keys to extract: {keys_str}

Rules:
- Return null for any field not clearly present in the input
- dob must be in YYYY-MM-DD format (convert "14th May 1990" → "1990-05-14")
- account_id must match pattern ACCXXXX (e.g. ACC1001)
- card_number: digits only, no spaces or dashes
- expiry_month: integer 1-12
- expiry_year: 4-digit integer (e.g. 2027)
- amount: return a numeric value. Accept inputs like "5", "5.00", "Rs 5", "₹5", "5 rupees", "5 ruppess"
- aadhaar: exactly 4 digits
- pincode: exactly 6 digits
- Return ONLY one JSON object (no prose, no markdown)
- Do NOT wrap response in markdown or backticks
- Include only requested keys

Example output:
{{"account_id": null, "name": "Nithin Jain", "dob": "1990-05-14"}}"""

        messages = [{"role": "user", "content": user_input}]

        try:
            raw = call_llm(system, messages)
            data = self._extract_first_json_object(raw)
            if data is None:
                LOGGER.warning("LLM extraction parse failed. Raw output: %r", raw)
                return {k: None for k in keys}
            return {k: data.get(k) for k in keys}
        except Exception as exc:
            LOGGER.exception("LLM extraction failed: %s", exc)
            return {k: None for k in keys}

    @staticmethod
    def _extract_first_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Extract and parse the first complete JSON object from LLM output.
        Handles wrappers such as prose and markdown fences.
        """
        if not isinstance(raw_text, str):
            return None

        start = raw_text.find("{")
        if start == -1:
            return None

        depth = 0
        for idx in range(start, len(raw_text)):
            char = raw_text[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw_text[start:idx + 1]
                    try:
                        parsed = json.loads(candidate)
                        return parsed if isinstance(parsed, dict) else None
                    except json.JSONDecodeError:
                        return None
        return None