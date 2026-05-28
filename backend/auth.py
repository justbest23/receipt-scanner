import os
import secrets
import string
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session

import database

_ph = PasswordHasher()

SESSION_DAYS        = int(os.getenv("SESSION_DAYS", "30"))
RATE_LIMIT_ATTEMPTS = 10
RATE_LIMIT_WINDOW   = 300  # seconds per window

_login_attempts: dict[str, list[float]] = defaultdict(list)
_join_attempts:  dict[str, list[float]] = defaultdict(list)

# Alphabet for invite codes — uppercase, no confusing chars (0/O, 1/I/L)
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
INVITE_HOURS   = int(os.getenv("INVITE_HOURS", "48"))


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False


def check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW
    fresh = [t for t in _login_attempts[ip] if t > cutoff]
    _login_attempts[ip] = fresh
    if len(fresh) >= RATE_LIMIT_ATTEMPTS:
        raise HTTPException(429, "Too many login attempts. Try again later.")


def record_attempt(ip: str) -> None:
    _login_attempts[ip].append(time.monotonic())


def check_join_rate_limit(ip: str) -> None:
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW
    fresh = [t for t in _join_attempts[ip] if t > cutoff]
    _join_attempts[ip] = fresh
    if len(fresh) >= RATE_LIMIT_ATTEMPTS:
        raise HTTPException(429, "Too many join attempts. Try again later.")


def record_join_attempt(ip: str) -> None:
    _join_attempts[ip].append(time.monotonic())


def generate_invite_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))


def create_session(db: Session, user_id: int, ip: str, user_agent: str) -> str:
    import models
    token = secrets.token_hex(32)
    sess = models.UserSession(
        user_id    = user_id,
        token      = token,
        expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS),
        ip_address = (ip or "")[:64],
        user_agent = (user_agent or "")[:512],
    )
    db.add(sess)
    db.commit()
    return token


def get_session(db: Session, token: Optional[str]):
    import models
    if not token:
        return None
    sess = db.query(models.UserSession).filter(models.UserSession.token == token).first()
    if not sess:
        return None
    exp = sess.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        db.delete(sess)
        db.commit()
        return None
    return sess


def get_current_user(request: Request, db: Session = Depends(database.get_db)):
    import models
    token = request.cookies.get("session")
    sess = get_session(db, token)
    if not sess:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.query(models.User).filter(models.User.id == sess.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(user=Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user


def require_permission(perm: str):
    def _dep(user=Depends(get_current_user)):
        if user.is_admin:
            return user
        if perm not in (user.permissions or []):
            raise HTTPException(403, f"Permission '{perm}' required")
        return user
    return _dep
