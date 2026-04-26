def verify_identity(account, provided_name, factor, factor_value):
    """
    Verifies user identity using:
    - Exact full name match (case-sensitive)
    - One secondary factor: dob / aadhaar / pincode

    Returns:
        (bool, str): (is_verified, message)
    """

    # --- Validate inputs ---
    if not account:
        return False, "Account information is missing. Please try again."

    if not provided_name:
        return False, "Full name is required for verification."

    if factor not in {"dob", "aadhaar", "pincode"}:
        return False, "Invalid verification method selected."

    if not factor_value:
        return False, "Verification detail is required."

    # --- Step 1: Name match (STRICT, case-sensitive) ---
    if provided_name != account.get("full_name"):
        return False, "Verification failed. The provided details do not match our records."

    # --- Step 2: Secondary factor match ---
    if factor == "dob":
        if factor_value != account.get("dob"):
            return False, "Verification failed. The provided details do not match our records."

    elif factor == "aadhaar":
        if factor_value != account.get("aadhaar_last4"):
            return False, "Verification failed. The provided details do not match our records."

    elif factor == "pincode":
        if factor_value != account.get("pincode"):
            return False, "Verification failed. The provided details do not match our records."

    # --- Success ---
    return True, "Identity verified successfully."