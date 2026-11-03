from datetime import datetime
from app.db import SessionLocal
from app.models import SyncRun, Trade, Withdrawal
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

def run_full_sync(triggered_by):
    db = SessionLocal()
    running = db.query(SyncRun).filter(SyncRun.status == "running").first()

    if running is not None:
        db.close()
        raise Exception("Sync already running")

    sync_run = SyncRun(
        sync_type="full",
        started_at=datetime.now().isoformat(),
        status="running",
        triggered_by=triggered_by,
    )
    db.add(sync_run)
    db.commit()

    try:
        client = get_client()
        total_commission,trade_count = sync_trades(db, client)
        total_withdrawals_count = sync_withdrawals(db, client)
        db.commit()

        sync_run.status = "success"
        sync_run.finished_at = datetime.now().isoformat()
        sync_run.rows_written = trade_count + total_withdrawals_count

        db.commit()

        return total_commission, trade_count, total_withdrawals_count

    except Exception as e:
        sync_run.status = "error"
        sync_run.finished_at = datetime.now().isoformat()
        sync_run.error_message = str(e)
        db.commit()
        raise

    finally:
        db.close()