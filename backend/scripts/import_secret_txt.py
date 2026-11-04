from app.db import SessionLocal
from app.crypto import encrypt_str
from pathlib import Path

from app.services.utils import load_secrets
from app.models import Credential
from datetime import datetime

SECRET_PATH = Path(__file__).resolve().parent.parent.parent / "Secret.txt"


if __name__ == "__main__":
    secrets = load_secrets(SECRET_PATH)
    # print("Loaded secrets:", secrets)
    encrypted_secrets = {key: encrypt_str(value) for key, value in secrets.items()}
    # print("Encrypted secrets:", encrypted_secrets)
    db = SessionLocal()
    secret_table = db.query(Credential).first()
    now = datetime.now().isoformat()

    if secret_table is None:
        new_credentials = Credential(
            id=1,
            key_id_encrypted=encrypted_secrets.get("POLYMARKET_KEY_ID"),
            secret_key_encrypted=encrypted_secrets.get("POLYMARKET_SECRET_KEY"),
            created_at=now,
            updated_at=now
        )
        db.add(new_credentials)
    else:
        secret_table.key_id_encrypted = encrypted_secrets.get("POLYMARKET_KEY_ID")
        secret_table.secret_key_encrypted = encrypted_secrets.get("POLYMARKET_SECRET_KEY")
        secret_table.updated_at = now
    db.commit()
    db.close()