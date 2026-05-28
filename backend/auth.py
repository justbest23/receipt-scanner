import logging
import os
import secrets
import smtplib
import string
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session

import database

logger = logging.getLogger("auth")

SMTP_HOST    = os.getenv("SMTP_HOST", "smtp.mail.yahoo.com")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER    = os.getenv("SMTP_USER", "")
SMTP_PASS    = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM    = os.getenv("SMTP_FROM", SMTP_USER)
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
ADMIN_EMAIL  = os.getenv("ADMIN_EMAIL", "")

_ph = PasswordHasher()

SESSION_DAYS        = int(os.getenv("SESSION_DAYS", "30"))
RATE_LIMIT_ATTEMPTS = 10
RATE_LIMIT_WINDOW   = 300  # seconds per window

_login_attempts:  dict[str, list[float]] = defaultdict(list)
_join_attempts:   dict[str, list[float]] = defaultdict(list)
_resend_attempts: dict[str, list[float]] = defaultdict(list)

RESEND_LIMIT  = 3
RESEND_WINDOW = 600  # 10 minutes

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


def check_resend_rate_limit(email: str) -> None:
    now = time.monotonic()
    cutoff = now - RESEND_WINDOW
    fresh = [t for t in _resend_attempts[email] if t > cutoff]
    _resend_attempts[email] = fresh
    if len(fresh) >= RESEND_LIMIT:
        raise HTTPException(429, f"Too many resend attempts. Try again in {RESEND_WINDOW // 60} minutes.")


def record_resend_attempt(email: str) -> None:
    _resend_attempts[email].append(time.monotonic())


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


def _send_email(to: str, subject: str, body_html: str) -> None:
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP not configured — skipping email to %s", to)
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_FROM or SMTP_USER
    msg["To"]      = to
    msg.attach(MIMEText(body_html, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.ehlo()
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_FROM or SMTP_USER, [to], msg.as_string())


def send_verification_email(to: str, token: str) -> None:
    url = f"{APP_BASE_URL}/auth/verify-email?token={token}"
    body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <h2 style="font-size:16px;letter-spacing:.06em;text-transform:uppercase;">Verify your Basket account</h2>
      <p style="color:#6b7280;margin:16px 0;">Click the button below to confirm your email address. The link expires in 24 hours.</p>
      <a href="{url}" style="display:inline-block;padding:12px 24px;background:#f97316;color:#fff;border-radius:3px;text-decoration:none;font-size:13px;letter-spacing:.05em;">Verify Email</a>
      <p style="color:#6b7280;font-size:11px;margin-top:24px;">Or copy this link: {url}</p>
    </div>"""
    _send_email(to, "Verify your Basket account", body)


def send_admin_registration_notice(admin_email: str, username: str, email: str) -> None:
    url = f"{APP_BASE_URL}/admin"
    body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <h2 style="font-size:16px;letter-spacing:.06em;text-transform:uppercase;">New registration request</h2>
      <p style="color:#6b7280;margin:16px 0;"><strong>{username}</strong> ({email}) has verified their email and is awaiting your approval.</p>
      <a href="{url}" style="display:inline-block;padding:12px 24px;background:#f97316;color:#fff;border-radius:3px;text-decoration:none;font-size:13px;letter-spacing:.05em;">Review in Admin</a>
    </div>"""
    _send_email(admin_email, f"Basket: new registration from {username}", body)


def require_permission(perm: str):
    def _dep(user=Depends(get_current_user)):
        if user.is_admin:
            return user
        if perm not in (user.permissions or []):
            raise HTTPException(403, f"Permission '{perm}' required")
        return user
    return _dep
