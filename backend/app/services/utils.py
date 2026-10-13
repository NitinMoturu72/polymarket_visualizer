from datetime import datetime
from decimal import Decimal, InvalidOperation


def load_secrets(path):
    """Load API credentials from secrets.txt."""

    secrets = {}

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                secrets[key.strip()] = value.strip()

    return secrets


def format_time(timestamp):
    """Convert API timestamp to local readable time."""

    if not timestamp:
        return ""

    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %I:%M:%S %p")
    except Exception:
        return timestamp


def dec(value, default="0"):
    """Safely parse an Amount-style value into a Decimal."""

    try:
        return Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def amt(amount_obj):
    """Pull the decimal value out of an {"value": "...", "currency": "USD"} dict."""

    if not amount_obj:
        return Decimal("0")
    return dec(amount_obj.get("value"))