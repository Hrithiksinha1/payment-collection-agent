from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from validators.card import luhn_check, validate_cvv, validate_expiry
from validators.amount import validate_amount
from validators.identity import verify_identity

FALSE_CASES_COUNT = 0


def _assert_false(result_tuple):
    """Assert validator returns False and track false-case count."""
    global FALSE_CASES_COUNT
    valid, _ = result_tuple
    assert valid is False
    FALSE_CASES_COUNT += 1


# ---------------------------
# Luhn Check Tests
# ---------------------------
def test_luhn_valid():
    assert luhn_check("4532015112830366") is True


def test_luhn_invalid():
    assert luhn_check("1234567890123456") is False


def test_luhn_empty():
    assert luhn_check("") is False


def test_luhn_non_numeric():
    assert luhn_check("4532abcd12830366") is False


# ---------------------------
# CVV Validation Tests
# ---------------------------
def test_validate_cvv_visa_valid():
    valid, _ = validate_cvv("123", "4532015112830366")  # Visa
    assert valid is True


def test_validate_cvv_amex_valid():
    valid, _ = validate_cvv("1234", "341234567890123")  # Amex
    assert valid is True


def test_validate_cvv_amex_invalid():
    _assert_false(validate_cvv("123", "341234567890123"))  # Amex needs 4


def test_validate_cvv_non_digit():
    _assert_false(validate_cvv("12a", "4532015112830366"))


def test_validate_cvv_empty():
    _assert_false(validate_cvv("", "4532015112830366"))


# ---------------------------
# Expiry Validation Tests
# ---------------------------
def test_validate_expiry_future():
    valid, _ = validate_expiry(12, 2099)
    assert valid is True


def test_validate_expiry_past():
    _assert_false(validate_expiry(1, 2020))


def test_validate_expiry_invalid_month_low():
    _assert_false(validate_expiry(0, 2099))


def test_validate_expiry_invalid_month_high():
    _assert_false(validate_expiry(13, 2099))


def test_validate_expiry_non_integer():
    _assert_false(validate_expiry("12", 2099))


# ---------------------------
# Amount Validation Tests
# ---------------------------
def test_validate_amount_valid():
    valid, _ = validate_amount(500, 1250.75)
    assert valid is True


def test_validate_amount_exceeds_balance():
    _assert_false(validate_amount(9999, 1250.75))


def test_validate_amount_zero():
    _assert_false(validate_amount(0, 1250.75))


def test_validate_amount_decimal_precision():
    _assert_false(validate_amount(100.999, 1250.75))


def test_validate_amount_negative():
    _assert_false(validate_amount(-50, 1250.75))


def test_validate_amount_invalid_format():
    _assert_false(validate_amount("abc", 1250.75))


def test_validate_amount_zero_balance():
    _assert_false(validate_amount(100, 0))


# ---------------------------
# Identity Verification Tests
# ---------------------------
@pytest.fixture
def sample_account():
    return {
        "account_id": "ACC1001",
        "full_name": "Nithin Jain",
        "dob": "1990-05-14",
        "aadhaar_last4": "4321",
        "pincode": "400001",
        "balance": 1250.75,
    }


def test_verify_identity_success(sample_account):
    valid, _ = verify_identity(
        sample_account,
        "Nithin Jain",
        "dob",
        "1990-05-14"
    )
    assert valid is True


def test_verify_identity_wrong_case(sample_account):
    _assert_false(verify_identity(
        sample_account,
        "nithin jain",  # wrong case
        "dob",
        "1990-05-14"
    ))


def test_verify_identity_wrong_factor(sample_account):
    _assert_false(verify_identity(
        sample_account,
        "Nithin Jain",
        "aadhaar",
        "9999"  # wrong value
    ))


def test_verify_identity_invalid_factor(sample_account):
    _assert_false(verify_identity(sample_account, "Nithin Jain", "email", "abc@example.com"))


def test_verify_identity_missing_name(sample_account):
    _assert_false(verify_identity(sample_account, "", "dob", "1990-05-14"))


def test_false_cases_count_snapshot():
    # This ensures false-path tests are present and counted.
    assert FALSE_CASES_COUNT >= 14


if __name__ == "__main__":
    # Direct-run summary and case logging (for `python tests/test_validators.py`).
    sample_account_data = {
        "full_name": "Nithin Jain",
        "dob": "1990-05-14",
        "aadhaar_last4": "4321",
        "pincode": "400001",
    }

    case_results = [
        ("luhn_valid", luhn_check("4532015112830366")),
        ("luhn_invalid_empty", luhn_check("")),
        ("luhn_invalid_non_numeric", luhn_check("abcd")),
        ("cvv_valid_visa", validate_cvv("123", "4532015112830366")[0]),
        ("cvv_valid_amex", validate_cvv("1234", "341234567890123")[0]),
        ("cvv_invalid_non_digit", validate_cvv("12a", "4532015112830366")[0]),
        ("cvv_invalid_amex_len", validate_cvv("123", "341234567890123")[0]),
        ("expiry_valid_future", validate_expiry(12, 2099)[0]),
        ("expiry_invalid_month", validate_expiry(0, 2099)[0]),
        ("amount_valid", validate_amount(500, 1250.75)[0]),
        ("amount_invalid_format", validate_amount("abc", 1250.75)[0]),
        ("amount_invalid_negative", validate_amount(-1, 1250.75)[0]),
        ("identity_valid", verify_identity(sample_account_data, "Nithin Jain", "dob", "1990-05-14")[0]),
        ("identity_invalid_name", verify_identity(sample_account_data, "nithin jain", "dob", "1990-05-14")[0]),
    ]

    true_cases = [name for name, result in case_results if result is True]
    false_cases = [name for name, result in case_results if result is False]

    log_file = PROJECT_ROOT / "tests" / "validation_case_log.txt"
    with log_file.open("w", encoding="utf-8") as file:
        file.write("Validation Case Run Log\n")
        file.write("=" * 30 + "\n")
        file.write(f"Total cases: {len(case_results)}\n")
        file.write(f"True cases count: {len(true_cases)}\n")
        file.write(f"False cases count: {len(false_cases)}\n\n")
        file.write("True cases:\n")
        for name in true_cases:
            file.write(f"- {name}\n")
        file.write("\nFalse cases:\n")
        for name in false_cases:
            file.write(f"- {name}\n")

    print(f"True cases count: {len(true_cases)}")
    print(f"False cases count: {len(false_cases)}")
    print(f"Case log file: {log_file}")