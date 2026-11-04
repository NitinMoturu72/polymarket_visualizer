from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import SyncRun
from app.services.sync import run_full_sync


router = APIRouter(prefix="/api/sync")

@router.post("")
def trigger_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    running = db.query(SyncRun).filter(SyncRun.status == "running").first()

    if running is not None:
        raise HTTPException(status_code=409, detail="A sync is already running.")

    background_tasks.add_task(run_full_sync, "manual")
    return {"status": "started"}

@router.get("/latest")
def get_latest_sync(db: Session = Depends(get_db)):
    latest_sync = db.query(SyncRun).order_by(SyncRun.started_at.desc()).first()

    if latest_sync is None:
        return {"status": "no syncs found"}

    return {
        "id": latest_sync.id,
        "sync_type": latest_sync.sync_type,
        "started_at": latest_sync.started_at,
        "status": latest_sync.status,
        "triggered_by": latest_sync.triggered_by
    }
