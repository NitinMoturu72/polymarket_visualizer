from fastapi import APIRouter,Depends

from app.db import get_db
from app.models import Trade
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/trades")

@router.get("")
def get_trades(db: Session = Depends(get_db)):
    trades = db.query(Trade).order_by(Trade.closed_at.desc()).all()
    rows = [
        {
            "id": t.id,
            "opened_at": t.opened_at,
            "closed_at": t.closed_at,
            "status": t.status,
            "market_title": t.market_title,
            "market_slug": t.market_slug,
            "outcome": t.outcome,
            "side_label": t.side_label,
            "qty": t.qty,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "commission": t.commission,
            "realized_pnl": t.realized_pnl,
            "note": t.note,
        }
        for t in trades
        ]
    return rows
