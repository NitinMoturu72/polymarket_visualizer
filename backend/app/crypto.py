from pathlib import Path
from cryptography.fernet import Fernet

KEY_PATH = Path(__file__).resolve().parent.parent / "data" / "encryption.key"


def load_or_create_key():
    if KEY_PATH.exists():
        with open(KEY_PATH, "rb") as key_file:
            ENCRYPTION_KEY = key_file.read()
    else:
        ENCRYPTION_KEY = Fernet.generate_key()
        with open(KEY_PATH, "wb") as key_file:
            key_file.write(ENCRYPTION_KEY)
    
    return ENCRYPTION_KEY.decode()

def encrypt_str(plain_txt):
    fernet = Fernet(KEY.encode())
    encrypted_txt = fernet.encrypt(plain_txt.encode())
    return encrypted_txt.decode()


def decrypt_str(encrypted_txt):
    fernet = Fernet(KEY.encode())
    decrypted_txt = fernet.decrypt(encrypted_txt.encode())
    return decrypted_txt.decode()


KEY = load_or_create_key()


if __name__ == "__main__":
    encrypted_key = encrypt_str(KEY)
    decrypted_key = decrypt_str(encrypted_key)

    if decrypted_key == KEY:
        print("Encryption and decryption successful.")

