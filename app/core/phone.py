"""Bangladeshi mobile number normalization and masking."""

import re

# re.ASCII stops \d from also matching Bengali digits.
PHONE_PATTERN = re.compile(r"01[3-9]\d{8}", re.ASCII)


def normalize_phone(value: str) -> str:
    """Convert a phone number to the 11-digit 01XXXXXXXXX form.

    Raises ValueError if it is not a valid Bangladeshi mobile number.
    """
    phone = re.sub(r"[\s-]", "", value)
    for country_prefix in ("+880", "880"):
        if phone.startswith(country_prefix):
            phone = "0" + phone.removeprefix(country_prefix)
            break

    if not PHONE_PATTERN.fullmatch(phone):
        raise ValueError(
            "Enter a valid Bangladeshi mobile number, for example 01712345678 "
            "or +8801712345678."
        )
    return phone


def mask_phone(phone: str) -> str:
    """Hide the middle digits, for example 01712345678 becomes 017****5678."""
    return f"{phone[:3]}****{phone[-4:]}"
