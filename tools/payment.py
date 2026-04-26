import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
import requests
from dotenv import load_dotenv


# --- Load environment variables ---
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL")


# --- Custom Exception ---
class ToolError(Exception):
    """Raised for all tool-related failures."""
    pass


ACCOUNT_ID_PATTERN = re.compile(r"^ACC\d{4}$")


def _normalize_account_id(account_id: str) -> str:
    if not isinstance(account_id, str):
        raise ToolError("Invalid account ID format. Please provide a valid account ID (e.g., ACC1001).")

    normalized = account_id.strip().upper()
    if not ACCOUNT_ID_PATTERN.fullmatch(normalized):
        raise ToolError("Invalid account ID format. Please provide a valid account ID (e.g., ACC1001).")
    return normalized


def _normalize_amount(amount: float) -> float:
    try:
        normalized = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ToolError("Invalid payment amount. Please provide a valid numeric amount.")

    if normalized <= Decimal("0"):
        raise ToolError("Invalid payment amount. Amount must be greater than zero.")

    if normalized.as_tuple().exponent < -2:
        raise ToolError("Invalid payment amount. Amount cannot have more than 2 decimal places.")

    return float(normalized)


def _normalize_card(card: dict) -> dict:
    if not isinstance(card, dict):
        raise ToolError("Invalid card details. Please provide complete card information.")

    required_keys = ["cardholder_name", "card_number", "cvv", "expiry_month", "expiry_year"]
    missing_keys = [key for key in required_keys if card.get(key) in (None, "")]
    if missing_keys:
        raise ToolError(
            f"Missing card details: {', '.join(missing_keys)}. Please provide complete card information."
        )

    cardholder_name = str(card["cardholder_name"]).strip()
    if not cardholder_name:
        raise ToolError("Invalid cardholder name. Please provide a valid cardholder name.")

    card_number = re.sub(r"[\s\-]", "", str(card["card_number"]))
    if not card_number.isdigit() or not (12 <= len(card_number) <= 19):
        raise ToolError("Invalid card number format. Please re-check your card number.")

    cvv = str(card["cvv"]).strip()
    if not cvv.isdigit() or len(cvv) not in (3, 4):
        raise ToolError("Invalid CVV format. CVV must be 3 or 4 digits.")

    try:
        expiry_month = int(str(card["expiry_month"]).strip())
        expiry_year = int(str(card["expiry_year"]).strip())
    except (TypeError, ValueError):
        raise ToolError("Invalid expiry date format. Please provide valid expiry month and year.")

    if expiry_month < 1 or expiry_month > 12:
        raise ToolError("Invalid expiry month. Please provide a month between 1 and 12.")

    now = datetime.now()
    min_year = now.year
    max_year = now.year + 25
    if expiry_year < min_year or expiry_year > max_year:
        raise ToolError("Invalid expiry year. Please provide a valid expiry year.")
    if expiry_year == now.year and expiry_month < now.month:
        raise ToolError("Card has expired. Please use a valid card.")

    return {
        "cardholder_name": cardholder_name,
        "card_number": card_number,
        "cvv": cvv,
        "expiry_month": expiry_month,
        "expiry_year": expiry_year,
    }


def process_payment(account_id: str, amount: float, card: dict) -> dict:
    """
    Processes payment using card details.

    Args:
        account_id (str)
        amount (float)
        card (dict): {
            "cardholder_name",
            "card_number",
            "cvv",
            "expiry_month",
            "expiry_year"
        }

    Returns:
        dict:
            On success: {"success": True, "transaction_id": str}
            On failure: {"success": False, "error_code": str}

    Raises:
        ToolError: for network/server/config errors
    """

    if not API_BASE_URL:
        raise ToolError("Service configuration error. Please try again later.")

    normalized_account_id = _normalize_account_id(account_id)
    normalized_amount = _normalize_amount(amount)
    normalized_card = _normalize_card(card)

    url = f"{API_BASE_URL}/api/process-payment"

    # --- Construct payload EXACTLY as required ---
    payload = {
        "account_id": normalized_account_id,
        "amount": normalized_amount,
        "payment_method": {
            "type": "card",
            "card": {
                "cardholder_name": normalized_card["cardholder_name"],
                "card_number": normalized_card["card_number"],
                "cvv": normalized_card["cvv"],
                "expiry_month": normalized_card["expiry_month"],
                "expiry_year": normalized_card["expiry_year"],
            },
        },
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
    except requests.RequestException:
        raise ToolError("Unable to process payment at the moment. Please try again later.")

    # --- Handle API responses ---
    if response.status_code == 200:
        data = response.json()
        return {
            "success": True,
            "transaction_id": data.get("transaction_id"),
        }

    if response.status_code == 422:
        data = response.json()
        return {
            "success": False,
            "error_code": data.get("error_code"),
        }

    # Any unexpected error
    raise ToolError("Payment service error. Please try again later.")