import os
import requests
from dotenv import load_dotenv


# --- Load environment variables ---
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL")


# --- Custom Exception ---
class ToolError(Exception):
    """Raised for all tool-related failures."""
    pass


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

    url = f"{API_BASE_URL}/api/process-payment"

    # --- Construct payload EXACTLY as required ---
    payload = {
        "account_id": account_id,
        "amount": amount,
        "payment_method": {
            "type": "card",
            "card": {
                "cardholder_name": card.get("cardholder_name"),
                "card_number": card.get("card_number"),
                "cvv": card.get("cvv"),
                "expiry_month": card.get("expiry_month"),
                "expiry_year": card.get("expiry_year"),
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