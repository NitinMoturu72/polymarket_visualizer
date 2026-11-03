from datetime import datetime
from app.db import SessionLocal
from app.models import Trade, Withdrawal
from app.polymarket_client import get_client
from app.services.pnl import fetch_trade_activities, build_rows
from app.services.withdrawals import fetch_withdrawal_activities, build_withdrawal_rows


def sync_trades(db,client):
    activities = fetch_trade_activities(client)
    rows, total_commission = build_rows(activities)
    now = datetime.now().isoformat()

    db.query(Trade).delete()

    for row in rows:
        db.add(Trade(
            opened_at=row["opened"],
            closed_at=row["closed"],
            status=row["status"],
            market_title=row["market"],
            market_slug=row["market_slug"],
            outcome=row["outcome"],
            side_label=row["side"],
            qty=str(row["qty"]),
            entry_price=str(row["entry_price"]) if row["entry_price"] is not None else None,
            exit_price=str(row["exit_price"]) if row["exit_price"] is not None else None,
            commission=str(row["commission"]),
            realized_pnl=str(row["realized_pnl"]),
            note=row["note"],
            synced_at=now,
        ))

    return total_commission,len(rows)


def sync_withdrawals(db, client):
    activities = fetch_withdrawal_activities(client)
    rows = build_withdrawal_rows(activities)
    now = datetime.now().isoformat()

    for row in rows:
        existing_withdrawal = db.get(Withdrawal, row["Transaction ID"])

        if existing_withdrawal is None:
            db.add(Withdrawal(
                transaction_id=row["Transaction ID"],
                external_id=row["External ID"],
                amount=str(row["Amount"]),
                currency=row["Currency"],
                status=row["Status"],
                created_at=row["Created"],
                updated_at=row["Updated"],
                description=row["Description"],
                failure_reason=row["Failure Reason"],
                failure_code=row["Failure Code"],
                synced_at=now,
            ))  
        else:
            existing_withdrawal.external_id = row["External ID"]
            existing_withdrawal.amount = str(row["Amount"])
            existing_withdrawal.currency = row["Currency"]
            existing_withdrawal.status = row["Status"]
            existing_withdrawal.created_at = row["Created"]
            existing_withdrawal.updated_at = row["Updated"]
            existing_withdrawal.description = row["Description"]
            existing_withdrawal.failure_reason = row["Failure Reason"]
            existing_withdrawal.failure_code = row["Failure Code"]
            existing_withdrawal.synced_at = now
        
    return len(rows)

def run_full_sync():
    db = SessionLocal()
    client = get_client()
    total_commission,trade_count = sync_trades(db, client)
    total_withdrawals = sync_withdrawals(db, client)
    db.commit()
    db.close()
    return total_commission, trade_count, total_withdrawals