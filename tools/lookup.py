import os
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

    url = f"{API_BASE_URL}/api/lookup-account"

    try:
        response = requests.post(
            url,
            json={"account_id": account_id},
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