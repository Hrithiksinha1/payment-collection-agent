import os
import re
import requests
from dotenv import load_dotenv


# --- Load environment variables ---
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL")


# --- Custom Exceptions ---
class AccountNotFoundError(Exception):
    """Raised when account is not found (404)."""
    pass


class ToolError(Exception):
    """Raised for all other tool-related failures."""
    pass


ACCOUNT_ID_PATTERN = re.compile(r"^ACC\d{4}$")


def _normalize_account_id(account_id: str) -> str:
    if not isinstance(account_id, str):
        raise ToolError("Invalid account ID format. Please provide a valid account ID (e.g., ACC1001).")

    normalized = account_id.strip().upper()
    if not ACCOUNT_ID_PATTERN.fullmatch(normalized):
        raise ToolError("Invalid account ID format. Please provide a valid account ID (e.g., ACC1001).")
    return normalized


# --- Tool Function ---
def lookup_account(account_id: str) -> dict:
    """
    Fetch account details using account_id.

    Returns:
        dict: Account data from API

    Raises:
        AccountNotFoundError: if account_id not found
        ToolError: for all other failures
    """

    if not API_BASE_URL:
        raise ToolError("Service configuration error. Please try again later.")

    normalized_account_id = _normalize_account_id(account_id)
    url = f"{API_BASE_URL}/api/lookup-account"

    try:
        response = requests.post(
            url,
            json={"account_id": normalized_account_id},
            timeout=5
        )
    except requests.RequestException:
        raise ToolError("Unable to reach the service. Please try again later.")

    # --- Response Handling ---
    if response.status_code == 200:
        return response.json()

    if response.status_code == 404:
        raise AccountNotFoundError("No account found with the provided account ID.")

    # Any unexpected error
    raise ToolError("Failed to fetch account details. Please try again.")