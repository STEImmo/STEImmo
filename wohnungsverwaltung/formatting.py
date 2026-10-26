from decimal import Decimal


def format_room_count(value: Decimal) -> str:
    """Display room counts with a decimal comma and no insignificant trailing zeros."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")
