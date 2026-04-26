from decimal import Decimal, InvalidOperation


def validate_amount(amount, balance) -> (bool, str):
    """
    Validates payment amount:
    - Must be > 0
    - Must be <= balance
    - Max 2 decimal places
    - Handle zero balance case
    """

    # --- Zero balance check ---
    try:
        balance = Decimal(str(balance))
    except (InvalidOperation, ValueError):
        return False, "Invalid balance value."

    if balance == Decimal("0.0"):
        return False, "There is no outstanding balance on this account."

    # --- Parse amount safely ---
    try:
        amt = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return False, "Invalid amount format."

    # --- Amount > 0 ---
    if amt <= Decimal("0"):
        return False, "Amount must be greater than zero."

    # --- Decimal precision check (max 2 places) ---
    if amt.as_tuple().exponent < -2:
        return False, "Amount cannot have more than 2 decimal places."

    # --- Amount <= balance ---
    if amt > balance:
        return False, "Amount exceeds the outstanding balance."

    return True, ""