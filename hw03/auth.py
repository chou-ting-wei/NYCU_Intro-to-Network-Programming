import hashlib
import os

def hash_password(password):
    salt = os.urandom(32)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return (salt + pwd_hash).hex()

def verify_password(stored_password, provided_password):
    stored_password_bytes = bytes.fromhex(stored_password)
    salt = stored_password_bytes[:32]
    stored_hash = stored_password_bytes[32:]
    pwd_hash = hashlib.pbkdf2_hmac('sha256', provided_password.encode(), salt, 100000)
    return pwd_hash == stored_hash
