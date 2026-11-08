"""
Module Xác thực Người dùng (Đăng ký, Đăng nhập, Quản lý Phiên & Bảo mật Mật khẩu).
Sử dụng thuật toán băm mật khẩu PBKDF2-HMAC-SHA256 kèm Salt ngẫu nhiên.
"""

import hashlib
import secrets
from datetime import datetime
from typing import Optional

from fastapi import Header, HTTPException
from backend.database import get_db


def hash_password(password: str, salt: Optional[str] = None) -> str:
    if not salt:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if "$" not in stored_hash:
        return False
    salt, _ = stored_hash.split("$", 1)
    return secrets.compare_digest(hash_password(password, salt), stored_hash)


def create_user_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, now_str),
    )
    conn.commit()
    conn.close()
    return token


def get_user_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    conn = get_db()
    row = conn.execute(
        """
        SELECT u.id, u.full_name, u.email, u.role, u.created_at
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ?
        """,
        (token,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def require_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập để sử dụng tính năng này.")
    token = authorization.replace("Bearer ", "", 1).strip()
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
    return user

