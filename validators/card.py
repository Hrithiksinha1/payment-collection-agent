from datetime import datetime


def luhn_check(card_number: str) -> bool:
    """
    Validates card number using Luhn algorithm.
    """
    if not card_number or not card_number.isdigit():
        return False

    digits = [int(d) for d in card_number]
    checksum = 0
    reverse_digits = digits[::-1]

    for i, digit in enumerate(reverse_digits):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit

    return checksum % 10 == 0


def validate_cvv(cvv: str, card_number: str) -> (bool, str):
    """
    Validates CVV based on card type.
    Amex (34/37) → 4 digits
    Others → 3 digits
    """
    if not cvv or not cvv.isdigit():
        return False, "Invalid CVV format."

    is_amex = card_number.startswith(("34", "37"))

    if is_amex and len(cvv) != 4:
        return False, "Invalid CVV. American Express cards require 4 digits."

    if not is_amex and len(cvv) != 3:
        return False, "Invalid CVV. CVV must be 3 digits."

    return True, ""


def validate_expiry(month: int, year: int) -> (bool, str):
    """
    Validates expiry date:
    - Month must be 1–12
    - Card must not be expired (relative to current date)
    """
    # Basic checks
    if not isinstance(month, int) or not isinstance(year, int):
        return False, "Invalid expiry date format."

    if month < 1 or month > 12:
        return False, "Invalid expiry month."

    # Get current date
    now = datetime.now()
    current_year = now.year
    current_month = now.month

    # Expiry logic: card is valid till end of expiry month
    if year < current_year:
        return False, "Card has expired."

    if year == current_year and month < current_month:
        return False, "Card has expired."

    return True, ""