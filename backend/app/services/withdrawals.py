from .utils import format_time

def fetch_all_activities(client):

    activities = []
    cursor = ""

    while True:
        params = {
            "limit": 100,
            "types": ["ACTIVITY_TYPE_ACCOUNT_WITHDRAWAL"],
        }

        if cursor:
            params["cursor"] = cursor

        response = client.portfolio.activities(params)
        batch = response.get("activities", [])
        activities.extend(batch)

        if response.get("eof", True) or not response.get("nextCursor"):
            break

        cursor = response["nextCursor"]

    return activities


def build_row(activity):

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

        return row

def build_withdrawal_rows(activities, existing=None):
    """Build a list of dicts for each withdrawal activity."""

    rows = dict(existing) if existing else {}

    for activity in activities:
        row = build_row(activity)
        rows[row["Transaction ID"]] = row

    rows = list(rows.values())
    rows.sort(key=lambda x: x.get("Created", ""), reverse=True)

    return rows