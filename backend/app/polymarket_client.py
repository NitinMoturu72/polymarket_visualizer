from app.db import SessionLocal
from app.crypto import decrypt_str

from app.models import Credential
from polymarket_us import PolymarketUS

def get_client():
    db = SessionLocal()
    secret_table = db.query(Credential).first()
    if secret_table is None:
        raise ValueError("No credentials found in the database.")
    else:
        key_id = decrypt_str(secret_table.key_id_encrypted)
        secret_key = decrypt_str(secret_table.secret_key_encrypted)
        return PolymarketUS(
                key_id=key_id, 
                secret_key=secret_key)
    
if __name__ == "__main__":
    client = get_client()
    print("Polymarket client initialized:", client)