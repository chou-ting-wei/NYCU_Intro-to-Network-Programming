# auth.py

import hashlib
import os

def hash_password(password):
    """使用 SHA-256 哈希密碼並添加隨機鹽"""
    salt = os.urandom(32)  # 生成一個 32 字節的鹽
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return salt + pwd_hash  # 將鹽和哈希結合

def verify_password(stored_password, provided_password):
    """驗證提供的密碼是否與存儲的哈希匹配"""
    salt = stored_password[:32]  # 提取鹽
    stored_hash = stored_password[32:]
    pwd_hash = hashlib.pbkdf2_hmac('sha256', provided_password.encode(), salt, 100000)
    return pwd_hash == stored_hash
