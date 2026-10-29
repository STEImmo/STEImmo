from decimal import ROUND_DOWN, Decimal


def format_area(value: Decimal) -> str:
    """Show one decimal place without rounding or changing the stored measurement."""
    return format(value.quantize(Decimal("0.1"), rounding=ROUND_DOWN), ".1f").replace(".", ",")


def format_room_count(value: Decimal) -> str:
    """Display room counts with a decimal comma and no insignificant trailing zeros."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")
