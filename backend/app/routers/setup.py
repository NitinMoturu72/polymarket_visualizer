from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from polymarket_us import PolymarketUS
from datetime import datetime
from app.db import get_db
from app.models import Credential   
from app.crypto import encrypt_str

router = APIRouter(prefix="/api/setup")

@router.get("/status")
def get_status(db:Session = Depends(get_db)):
    credential = db.get(Credential,1)
    return {"configured": credential is not None}

class CredentialsIn(BaseModel):
    key_id: str
    secret_key: str

@router.post("/credentials")
def set_credentials(payload: CredentialsIn, db: Session = Depends(get_db)):
    try:
        test_client = PolymarketUS(
                        key_id = payload.key_id, 
                        secret_key = payload.secret_key)
        test_client.portfolio.activities({"limit": 1, "types": ["ACTIVITY_TYPE_ACCOUNT_WITHDRAWAL"]})
        test_client.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    secret_table = db.get(Credential, 1)
    now = datetime.now().isoformat()
    if secret_table is None:
        new_credentials = Credential(
            id=1,
            key_id_encrypted=encrypt_str(payload.key_id),
            secret_key_encrypted=encrypt_str(payload.secret_key),
            created_at=now,
            updated_at=now
        )
        db.add(new_credentials)
    else:
        secret_table.key_id_encrypted = encrypt_str(payload.key_id)
        secret_table.secret_key_encrypted = encrypt_str(payload.secret_key)
        secret_table.updated_at = now
    db.commit()