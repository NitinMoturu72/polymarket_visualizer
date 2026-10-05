import os
import csv
from datetime import datetime
from polymarket_us import PolymarketUS

CSV_FILE = "polymarket_withdrawals.csv"
SECRETS_FILE = "Secret.txt"


def load_secrets():
    """Load API credentials from secrets.txt."""

    secrets = {}

    with open(SECRETS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                secrets[key.strip()] = value.strip()

    return secrets


# Load credentials
secrets = load_secrets()

key_id = secrets["POLYMARKET_KEY_ID"]
secret_key = secrets["POLYMARKET_SECRET_KEY"]


client = PolymarketUS(
    key_id=key_id,
    secret_key=secret_key,
)


def format_time(timestamp):
    """Convert API timestamp to local readable time."""

    if not timestamp:
        return ""

    try:
        dt = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )

        return dt.astimezone().strftime(
            "%Y-%m-%d %I:%M:%S %p"
        )

    except Exception:
        return timestamp


try:

    # Get all withdrawal activities
    response = client.portfolio.activities({
        "limit": 100,
        "types": ["ACTIVITY_TYPE_ACCOUNT_WITHDRAWAL"]
    })

    activities = response.get("activities", [])

    # ---------------------------------------------------------
    # Load existing CSV
    # ---------------------------------------------------------

    existing = {}

    if os.path.exists(CSV_FILE):

        with open(
            CSV_FILE,
            "r",
            newline="",
            encoding="utf-8-sig"
        ) as f:

            reader = csv.DictReader(f)

            for row in reader:

                transaction_id = row.get(
                    "Transaction ID"
                )

                if transaction_id:
                    existing[transaction_id] = row


    # ---------------------------------------------------------
    # Process withdrawals from Polymarket
    # ---------------------------------------------------------

    for activity in activities:

        balance_change = activity.get(
            "accountBalanceChange",
            {}
        )

        transaction_id = balance_change.get(
            "transactionId",
            ""
        )

        status = balance_change.get(
            "status",
            ""
        )

        amount = balance_change.get(
            "amount",
            {}
        )

        external_id = balance_change.get(
            "externalId",
            ""
        )

        description = balance_change.get(
            "description",
            ""
        )

        create_time = balance_change.get(
            "createTime",
            ""
        )

        update_time = balance_change.get(
            "updateTime",
            ""
        )

        failure_reason = balance_change.get(
            "failureReason",
            ""
        )

        failure_code = balance_change.get(
            "failureCode",
            ""
        )

        amount_value = amount.get(
            "value",
            ""
        )

        currency = amount.get(
            "currency",
            ""
        )


        row = {
            "Transaction ID": transaction_id,
            "External ID": external_id,
            "Amount": amount_value,
            "Currency": currency,
            "Status": status.replace(
                "ACCOUNT_BALANCE_CHANGE_STATUS_",
                ""
            ),
            "Created": format_time(create_time),
            "Updated": format_time(update_time),
            "Description": description,
            "Failure Reason": failure_reason,
            "Failure Code": failure_code,
        }


        # Add new transaction or update existing one
        existing[transaction_id] = row


    # ---------------------------------------------------------
    # Sort newest first
    # ---------------------------------------------------------

    rows = list(existing.values())

    rows.sort(
        key=lambda x: x.get("Created", ""),
        reverse=True
    )


    # ---------------------------------------------------------
    # Write back to SAME CSV
    # ---------------------------------------------------------

    fieldnames = [
        "Transaction ID",
        "External ID",
        "Amount",
        "Currency",
        "Status",
        "Created",
        "Updated",
        "Description",
        "Failure Reason",
        "Failure Code",
    ]


    with open(
        CSV_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)


    # ---------------------------------------------------------
    # Calculate totals
    # ---------------------------------------------------------

    total = 0.0
    completed = 0.0
    pending = 0.0

    for row in rows:

        try:
            value = float(row["Amount"])
        except (ValueError, TypeError):
            continue

        total += value

        if row["Status"] == "COMPLETED":
            completed += value

        elif row["Status"] == "PENDING":
            pending += value


    # ---------------------------------------------------------
    # Display result
    # ---------------------------------------------------------

    print()
    print("========================================")
    print(" Polymarket Withdrawal Report Updated")
    print("========================================")

    print(f"Total withdrawals:       {len(rows)}")
    print(f"Total withdrawn/requested: ${total:,.2f}")
    print(f"Completed:                 ${completed:,.2f}")
    print(f"Pending:                   ${pending:,.2f}")

    print()
    print(f"CSV: {os.path.abspath(CSV_FILE)}")
    print()


finally:

    client.close()