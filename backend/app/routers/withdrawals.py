from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Withdrawal

from app.services.utils import dec

router = APIRouter(prefix="/api/withdrawals")

@router.get("")
def get_withdrawals(db: Session = Depends(get_db)):
    withdrawals = db.query(Withdrawal).order_by(Withdrawal.created_at.desc()).all()
    rows = [
        {
            "transaction_id": w.transaction_id,
            "external_id": w.external_id,
            "amount": w.amount,
            "currency": w.currency,
            "status": w.status,
            "created_at": w.created_at,
            "updated_at": w.updated_at,
            "description": w.description,
            "failure_reason": w.failure_reason,
            "failure_code": w.failure_code,
            "synced_at": w.synced_at
        }
        for w in withdrawals
    ]
    return rows

@router.get("/summary")
def get_withdrawal_summary(db: Session = Depends(get_db)):
    withdrawals = db.query(Withdrawal).all()

    total_amount = sum(dec(w.amount) for w in withdrawals if w.status == "COMPLETED")

    return {
        "total_amount": str(total_amount),
        "withdrawal_count": len(withdrawals)
    }