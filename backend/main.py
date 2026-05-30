"""
main.py — Receipt Scanner + Price Tracker API v0.4

Receipt flow:
  POST /scan              → run pipeline, return extracted data (no DB save)
  POST /receipts/confirm  → save reviewed result to DB
  GET  /receipts          → paginated list
  GET  /receipts/{id}     → single receipt with items
  DELETE /receipts/{id}

Price tracking:
  GET  /prices/search?q=  → search all stores (returns cached + triggers bg scrape)
  POST /prices/scrape     → force-refresh a query across all stores
  GET  /prices/history?q= → all stored results for a query (any age)
  POST /prices/uitkyk/import → import Uitkyk CSV

Meal planning:
  GET  /meals/recipes           → list recipes
  POST /meals/recipes           → create recipe
  GET  /meals/recipes/{id}      → single recipe
  DELETE /meals/recipes/{id}
  POST /meals/recipes/{id}/ingredients → add ingredient
  DELETE /meals/ingredients/{id}
  GET  /meals/shopping?recipe_ids=1,2  → shopping list with cheapest store per item
"""

import asyncio
import io
import os
import re
import secrets
import uuid
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

import auth
import database
import models
from pipeline import run_pipeline, check_ollama_health
from claude_pipeline import run_claude_pipeline
from vendor import list_vendors
import scraper_service
from normalizer import normalize_names

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger("main")

UPLOAD_DIR    = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/tiff", "application/pdf", "text/csv", "application/csv", "text/plain"}
MAX_SIZE_MB   = 20

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _parse_csv_receipt(content: str) -> dict:
    """Parse a PnP/Checkers-style receipt CSV into pipeline-result format."""
    import csv, re, io
    reader = csv.reader(io.StringIO(content))
    rows = [r for r in reader if any(c.strip() for c in r)]

    items = []
    total = None
    for row in rows:
        if len(row) < 2:
            continue
        name_col = row[0].strip()
        cost_col = row[-1].strip() if len(row) >= 2 else ""

        # Skip header rows
        if name_col.lower() in ("item", "description", "count"):
            continue

        # Look for total line
        if re.match(r"(total|amount due|subtotal)", name_col, re.I):
            m = re.search(r"[\d.]+", cost_col.replace(",", ""))
            if m:
                total = float(m.group())
            continue

        # Parse cost — strip R, A (VAT flag), spaces
        cost_str = re.sub(r"[R\sA]", "", cost_col).replace(",", "")
        try:
            price = float(cost_str)
        except ValueError:
            continue

        # Parse quantity from count column (e.g. "2 @ R1.40" or "2 @ 1.40")
        qty = 1.0
        unit_price = None
        count_col = row[1].strip() if len(row) >= 3 else ""
        m = re.match(r"([\d.]+)\s*@\s*R?([\d.]+)", count_col)
        if m:
            qty = float(m.group(1))
            unit_price = float(m.group(2))

        vat = cost_col.endswith("A") or "A" in cost_col[-2:]
        items.append({
            "name":           name_col,
            "quantity":       qty,
            "unit_type":      "unit",
            "unit_price":     unit_price or (round(price / qty, 2) if qty > 1 else price),
            "total_price":    price,
            "vat_applicable": vat,
            "confidence":     1.0,
        })

    if total is None and items:
        total = round(sum(i["total_price"] for i in items), 2)

    return {
        "extracted": {
            "store": {"name": None, "confidence": 0},
            "date":  {"value": None, "confidence": 0},
            "items": items,
            "total": total,
            "subtotal": None,
            "vat_total": None,
            "currency": "ZAR",
        },
        "vendor": "csv_import",
        "source": "csv",
    }


def _pdf_to_image(pdf_path: Path) -> Path:
    """Convert the first page of a PDF to a JPEG and return the new path."""
    try:
        import fitz  # PyMuPDF
        doc  = fitz.open(str(pdf_path))
        page = doc[0]
        mat  = fitz.Matrix(2, 2)  # 2× zoom → ~150 dpi
        pix  = page.get_pixmap(matrix=mat)
        out  = pdf_path.with_suffix(".jpg")
        pix.save(str(out))
        doc.close()
        return out
    except ImportError:
        raise HTTPException(500, "PDF conversion unavailable — PyMuPDF not installed")


app = FastAPI(title="Receipt Scanner", version="0.3.0")


@app.on_event("startup")
def startup():
    logger.info("Initialising database…")
    database.init_db()
    logger.info("Database ready")
    ollama = check_ollama_health()
    if not ollama["reachable"]:
        logger.warning(f"Ollama not reachable: {ollama.get('error')}")
    elif not ollama.get("model_loaded"):
        logger.warning(f"Model '{ollama['configured_model']}' not found. Run: docker exec receipt-ollama ollama pull {ollama['configured_model']}")
    else:
        logger.info(f"Ollama ready — {ollama['configured_model']}")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/download/basket.apk")
def download_apk():
    from fastapi.responses import FileResponse
    return FileResponse(
        "static/basket.apk",
        media_type="application/vnd.android.package-archive",
        headers={"Content-Disposition": 'attachment; filename="basket.apk"'},
    )


def _session_user(request: Request, db: Session):
    """Return User if session cookie is valid, else None."""
    token = request.cookies.get("session")
    sess = auth.get_session(db, token)
    if not sess:
        return None
    user = db.query(models.User).filter(models.User.id == sess.user_id).first()
    return user if (user and user.is_active) else None


def _html(request: Request, db: Session, page: str):
    """Serve an HTML page, redirecting to /login if not authenticated."""
    user = _session_user(request, db)
    if not user:
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
    return (Path("static") / page).read_text()


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request, db: Session = Depends(database.get_db)):
    if _session_user(request, db):
        return RedirectResponse("/", status_code=303)
    return (Path("static") / "login.html").read_text()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def frontend(request: Request, db: Session = Depends(database.get_db)):
    return _html(request, db, "index.html")

@app.get("/history", response_class=HTMLResponse, include_in_schema=False)
def history_page(request: Request, db: Session = Depends(database.get_db)):
    return _html(request, db, "history.html")

@app.get("/prices", response_class=HTMLResponse, include_in_schema=False)
def prices_page(request: Request, db: Session = Depends(database.get_db)):
    return _html(request, db, "prices.html")

@app.get("/meals", response_class=HTMLResponse, include_in_schema=False)
def meals_page(request: Request, db: Session = Depends(database.get_db)):
    return _html(request, db, "meals.html")


@app.get("/health")
def health(db: Session = Depends(database.get_db)):
    from sqlalchemy import text
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"api": "ok", "db": "ok" if db_ok else "error", "ollama": check_ollama_health()}


@app.get("/vendors")
def vendors(user: models.User = Depends(auth.get_current_user)):
    return {"vendors": list_vendors()}


# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_page(request: Request, db: Session = Depends(database.get_db)):
    if _session_user(request, db):
        return RedirectResponse("/", status_code=303)
    return (Path("static") / "register.html").read_text()


@app.post("/auth/register")
def register(request: Request, payload: dict, db: Session = Depends(database.get_db)):
    import re
    from sqlalchemy import or_, func as sqlfunc

    username     = (payload.get("username") or "").strip().lower()
    email        = (payload.get("email") or "").strip().lower()
    password     = payload.get("password") or ""
    display_name = (payload.get("display_name") or "").strip() or None

    if not username or not email or not password:
        raise HTTPException(400, "username, email, and password are required")
    if not re.match(r"^[a-z0-9_\-]{3,32}$", username):
        raise HTTPException(400, "Username must be 3–32 characters: letters, numbers, _ or -")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "Invalid email address")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    conflict_user = db.query(models.User).filter(
        or_(sqlfunc.lower(models.User.username) == username,
            sqlfunc.lower(models.User.email) == email)
    ).first()
    if conflict_user:
        raise HTTPException(409, "Username or email already in use")

    conflict_req = db.query(models.RegistrationRequest).filter(
        or_(models.RegistrationRequest.username == username,
            models.RegistrationRequest.email == email),
        models.RegistrationRequest.status.in_(["pending_email", "pending_admin"]),
    ).first()
    if conflict_req:
        raise HTTPException(409, "A pending registration already exists for this username or email")

    token = secrets.token_urlsafe(32)
    req = models.RegistrationRequest(
        username      = username,
        email         = email,
        display_name  = display_name,
        password_hash = auth.hash_password(password),
        email_token   = token,
        status        = "pending_email",
    )
    db.add(req)
    db.commit()

    try:
        auth.send_verification_email(email, token)
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {e}")

    return {"ok": True, "message": "Check your email to verify your address."}


@app.post("/auth/resend-verification")
def resend_verification(request: Request, payload: dict, db: Session = Depends(database.get_db)):
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "email is required")

    auth.check_resend_rate_limit(email)
    auth.record_resend_attempt(email)

    req = db.query(models.RegistrationRequest).filter(
        models.RegistrationRequest.email == email,
        models.RegistrationRequest.status == "pending_email",
    ).first()

    # Always return the same response to avoid leaking whether an email exists
    if req:
        new_token = secrets.token_urlsafe(32)
        req.email_token = new_token
        db.commit()
        try:
            auth.send_verification_email(email, new_token)
        except Exception as e:
            logger.error(f"Failed to resend verification email to {email}: {e}")

    return {"ok": True, "message": "If a pending registration exists for that email, a new verification link has been sent."}


@app.get("/auth/verify-email", response_class=HTMLResponse, include_in_schema=False)
def verify_email(token: str, db: Session = Depends(database.get_db)):
    req = db.query(models.RegistrationRequest).filter(
        models.RegistrationRequest.email_token == token
    ).first()

    def _page(title: str, body: str) -> str:
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
        <title>{title} — Basket</title>
        <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
        <style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#0d0f11;color:#e2e4e7;font-family:'DM Sans',sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}}.card{{background:#141618;border:1px solid #2a2d32;border-radius:4px;padding:40px 36px;max-width:400px;width:100%;text-align:center}}h1{{font-family:'Space Mono',monospace;font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:#6b7280;margin-bottom:16px}}p{{font-size:14px;color:#6b7280;line-height:1.6;margin-bottom:20px}}a{{color:#f97316;text-decoration:none}}</style>
        </head><body><div class="card"><h1>{title}</h1>{body}</div></body></html>"""

    if not req:
        return HTMLResponse(_page("Invalid Link", "<p>This verification link is invalid or has already been used.</p><p><a href='/login'>Back to sign in</a></p>"), status_code=400)

    if req.status == "approved":
        return HTMLResponse(_page("Already Approved", "<p>Your account has already been approved. <a href='/login'>Sign in</a></p>"))

    if req.status == "denied":
        return HTMLResponse(_page("Registration Denied", "<p>Your registration was not approved.</p>"))

    if req.email_verified:
        return HTMLResponse(_page("Already Verified", "<p>Your email is verified and your registration is awaiting admin approval.</p>"))

    req.email_verified = True
    req.status = "pending_admin"
    db.commit()

    if auth.ADMIN_EMAIL:
        try:
            auth.send_admin_registration_notice(auth.ADMIN_EMAIL, req.username, req.email)
        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")

    return HTMLResponse(_page("Email Verified", "<p>Your email address is confirmed. Your registration is now pending admin approval — you'll be able to sign in once it's approved.</p><p><a href='/login'>Back to sign in</a></p>"))


@app.get("/admin/receipts")
def admin_list_receipts(
    user_id: Optional[int] = Query(default=None),
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    q = db.query(models.Receipt).order_by(models.Receipt.created_at.desc())
    if user_id is not None:
        q = q.filter(models.Receipt.user_id == user_id)
    return [
        {
            "id":       r.id,
            "user_id":  r.user_id,
            "store":    r.store_name,
            "date":     r.receipt_date,
            "total":    r.total,
            "currency": r.currency,
            "items":    len(r.items),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in q.limit(500).all()
    ]


@app.post("/admin/receipts/reassign")
def admin_reassign_receipts(
    payload: dict,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    receipt_ids = [int(i) for i in (payload.get("receipt_ids") or [])]
    to_user_id  = payload.get("to_user_id")
    if not receipt_ids:
        raise HTTPException(400, "receipt_ids is required")
    if to_user_id is None:
        raise HTTPException(400, "to_user_id is required")

    target = db.query(models.User).filter(models.User.id == int(to_user_id), models.User.is_active == True).first()  # noqa: E712
    if not target:
        raise HTTPException(404, "Target user not found or inactive")

    updated = db.query(models.Receipt).filter(models.Receipt.id.in_(receipt_ids)).update(
        {"user_id": target.id}, synchronize_session=False
    )
    db.commit()
    logger.info(f"Admin '{admin.username}' reassigned {updated} receipt(s) to user '{target.username}'")
    return {"reassigned": updated, "to_user": target.username}


@app.get("/admin/registrations")
def admin_list_registrations(
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    reqs = db.query(models.RegistrationRequest).order_by(
        models.RegistrationRequest.created_at.desc()
    ).all()
    return [_reg_dict(r) for r in reqs]


@app.post("/admin/registrations/{req_id}/approve")
def admin_approve_registration(
    req_id: int,
    payload: dict = None,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    from sqlalchemy import or_, func as sqlfunc
    payload = payload or {}
    req = db.query(models.RegistrationRequest).filter(models.RegistrationRequest.id == req_id).first()
    if not req:
        raise HTTPException(404, "Registration not found")
    if req.status != "pending_admin":
        raise HTTPException(400, f"Cannot approve a request with status '{req.status}'")

    conflict = db.query(models.User).filter(
        or_(sqlfunc.lower(models.User.username) == req.username,
            sqlfunc.lower(models.User.email) == req.email)
    ).first()
    if conflict:
        raise HTTPException(409, "Username or email already taken by an existing user")

    perms = payload.get("permissions") or ["scan", "history", "prices", "meals", "analytics"]
    user = models.User(
        username       = req.username,
        email          = req.email,
        email_verified = True,
        display_name   = req.display_name,
        password_hash  = req.password_hash,
        is_admin       = False,
        is_active      = True,
        permissions    = perms,
    )
    db.add(user)
    req.status      = "approved"
    req.reviewed_at = datetime.now(timezone.utc)
    req.reviewed_by = admin.id
    db.commit()
    logger.info(f"Admin '{admin.username}' approved registration for '{req.username}'")
    return {"ok": True}


@app.post("/admin/registrations/{req_id}/deny")
def admin_deny_registration(
    req_id: int,
    payload: dict = None,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    payload = payload or {}
    req = db.query(models.RegistrationRequest).filter(models.RegistrationRequest.id == req_id).first()
    if not req:
        raise HTTPException(404, "Registration not found")
    if req.status not in ("pending_email", "pending_admin"):
        raise HTTPException(400, f"Cannot deny a request with status '{req.status}'")

    req.status        = "denied"
    req.denial_reason = (payload.get("reason") or "").strip() or None
    req.reviewed_at   = datetime.now(timezone.utc)
    req.reviewed_by   = admin.id
    db.commit()
    logger.info(f"Admin '{admin.username}' denied registration for '{req.username}'")
    return {"ok": True}


@app.post("/auth/login")
def login(request: Request, payload: dict, db: Session = Depends(database.get_db)):
    ip = request.client.host if request.client else "unknown"
    auth.check_rate_limit(ip)

    identifier = (payload.get("username") or "").strip().lower()
    password = payload.get("password") or ""
    if not identifier or not password:
        auth.record_attempt(ip)
        raise HTTPException(401, "Invalid credentials")

    from sqlalchemy import or_, func as sqlfunc
    user = db.query(models.User).filter(
        or_(sqlfunc.lower(models.User.username) == identifier,
            sqlfunc.lower(models.User.email) == identifier)
    ).first()
    if not user or not user.is_active or not auth.verify_password(password, user.password_hash):
        auth.record_attempt(ip)
        raise HTTPException(401, "Invalid credentials")

    token = auth.create_session(
        db, user.id,
        ip=ip,
        user_agent=request.headers.get("user-agent", ""),
    )
    # Use Secure flag only when the client reached us over HTTPS (via reverse proxy)
    is_https = request.headers.get("x-forwarded-proto", "").lower() == "https"
    response = JSONResponse({"ok": True, "username": user.username, "is_admin": user.is_admin, "token": token})
    response.set_cookie(
        "session", token,
        httponly=True,
        secure=is_https,
        samesite="strict",
        max_age=auth.SESSION_DAYS * 86400,
    )
    return response


@app.post("/auth/logout")
def logout(request: Request, db: Session = Depends(database.get_db)):
    token = request.cookies.get("session")
    if token:
        sess = auth.get_session(db, token)
        if sess:
            db.delete(sess)
            db.commit()
    response = JSONResponse({"ok": True})
    response.delete_cookie("session", httponly=True, samesite="strict")
    return response


@app.patch("/auth/profile")
def update_profile(
    payload: dict,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    import re
    from sqlalchemy import func as sqlfunc

    if "display_name" in payload:
        user.display_name = (payload["display_name"] or "").strip() or None

    if "username" in payload:
        new_un = (payload["username"] or "").strip().lower()
        if new_un and new_un != user.username:
            if not re.match(r"^[a-z0-9_\-]{3,32}$", new_un):
                raise HTTPException(400, "Username must be 3–32 characters: letters, numbers, _ or -")
            if db.query(models.User).filter(sqlfunc.lower(models.User.username) == new_un, models.User.id != user.id).first():
                raise HTTPException(409, "Username already taken")
            user.username = new_un

    if "email" in payload:
        new_email = (payload["email"] or "").strip().lower()
        if new_email and new_email != (user.email or ""):
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", new_email):
                raise HTTPException(400, "Invalid email address")
            if db.query(models.User).filter(sqlfunc.lower(models.User.email) == new_email, models.User.id != user.id).first():
                raise HTTPException(409, "Email already in use")
            user.email = new_email

    if "password" in payload:
        pw = (payload["password"] or "").strip()
        if pw:
            if len(pw) < 8:
                raise HTTPException(400, "Password must be at least 8 characters")
            user.password_hash = auth.hash_password(pw)

    if "currency" in payload:
        cur = (payload["currency"] or "").strip().upper()
        if cur:
            user.currency = cur

    db.commit()
    db.refresh(user)
    logger.info(f"User '{user.username}' updated their profile")
    return _user_dict(user)


@app.get("/auth/me")
def auth_me(user: models.User = Depends(auth.get_current_user)):
    return {
        "id":           user.id,
        "username":     user.username,
        "email":        user.email,
        "display_name": user.display_name,
        "is_admin":     user.is_admin,
        "permissions":  user.permissions or [],
        "currency":     user.currency or "ZAR",
    }


# ── Admin user management ─────────────────────────────────────────────────────

ALL_PERMISSIONS = ["scan", "history", "prices", "meals", "analytics"]


@app.get("/admin/users")
def admin_list_users(admin: models.User = Depends(auth.require_admin), db: Session = Depends(database.get_db)):
    users = db.query(models.User).order_by(models.User.created_at).all()
    return [_user_dict(u) for u in users]


@app.post("/admin/users")
def admin_create_user(
    payload: dict,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    username = (payload.get("username") or "").strip().lower()
    password = (payload.get("password") or "").strip()
    if not username or not password:
        raise HTTPException(400, "username and password are required")
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(409, f"Username '{username}' already exists")

    perms = [p for p in (payload.get("permissions") or []) if p in ALL_PERMISSIONS]
    user = models.User(
        username      = username,
        display_name  = (payload.get("display_name") or "").strip() or None,
        password_hash = auth.hash_password(password),
        is_admin      = bool(payload.get("is_admin", False)),
        is_active     = True,
        permissions   = perms,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"Admin '{admin.username}' created user '{username}'")
    return _user_dict(user)


@app.get("/admin/users/{user_id}")
def admin_get_user(
    user_id: int,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    return _user_dict(u)


@app.patch("/admin/users/{user_id}")
def admin_update_user(
    user_id: int,
    payload: dict,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")

    if "display_name" in payload:
        u.display_name = (payload["display_name"] or "").strip() or None
    if "is_admin" in payload:
        if u.id == admin.id and not payload["is_admin"]:
            raise HTTPException(400, "Cannot remove your own admin rights")
        u.is_admin = bool(payload["is_admin"])
    if "is_active" in payload:
        if u.id == admin.id and not payload["is_active"]:
            raise HTTPException(400, "Cannot deactivate your own account")
        u.is_active = bool(payload["is_active"])
    if "permissions" in payload:
        u.permissions = [p for p in (payload["permissions"] or []) if p in ALL_PERMISSIONS]
    if "password" in payload:
        pw = (payload["password"] or "").strip()
        if len(pw) < 8:
            raise HTTPException(400, "Password must be at least 8 characters")
        u.password_hash = auth.hash_password(pw)

    db.commit()
    db.refresh(u)
    logger.info(f"Admin '{admin.username}' updated user '{u.username}'")
    return _user_dict(u)


@app.delete("/admin/users/{user_id}")
def admin_delete_user(
    user_id: int,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "Cannot delete your own account")
    db.delete(u)
    db.commit()
    logger.info(f"Admin '{admin.username}' deleted user '{u.username}'")
    return {"deleted": user_id}


# ── Scan (no DB save) ─────────────────────────────────────────────────────────
@app.post("/scan")
def scan_receipt(
    file: UploadFile = File(...),
    model: str | None = Query(None),
    user: models.User = Depends(auth.require_permission("scan")),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    content = file.file.read()
    if len(content) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {MAX_SIZE_MB} MB)")

    ext        = Path(file.filename or "receipt.jpg").suffix or ".jpg"
    filename   = f"{uuid.uuid4()}{ext}"
    image_path = UPLOAD_DIR / filename
    image_path.write_bytes(content)

    if file.content_type == "application/pdf":
        image_path = _pdf_to_image(image_path)

    logger.info(f"Processing {image_path.name} ({len(content)/1024:.1f} KB)" + (f" [{model}]" if model else ""))

    try:
        result = run_pipeline(str(image_path), model=model)
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        raise HTTPException(500, f"Pipeline failed: {e}")

    return result


@app.post("/scan/claude")
def scan_receipt_claude(
    file: UploadFile = File(...),
    user: models.User = Depends(auth.require_permission("scan")),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    content = file.file.read()
    if len(content) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {MAX_SIZE_MB} MB)")

    ext        = Path(file.filename or "receipt.jpg").suffix or ".jpg"
    filename   = f"{uuid.uuid4()}{ext}"
    image_path = UPLOAD_DIR / filename
    image_path.write_bytes(content)

    if file.content_type == "application/pdf":
        image_path = _pdf_to_image(image_path)

    logger.info(f"Claude scan: {image_path.name} ({len(content)/1024:.1f} KB)")

    try:
        result = run_claude_pipeline(str(image_path))
    except Exception as e:
        logger.error(f"Claude pipeline error: {e}", exc_info=True)
        raise HTTPException(500, f"Claude pipeline failed: {e}")

    return result


@app.post("/scan/csv")
async def scan_receipt_csv(
    file: UploadFile = File(...),
    user: models.User = Depends(auth.require_permission("scan")),
):
    content_bytes = await file.read()
    if len(content_bytes) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 5 MB)")
    try:
        text = content_bytes.decode("utf-8", errors="replace")
        result = _parse_csv_receipt(text)
    except Exception as e:
        logger.error(f"CSV parse error: {e}", exc_info=True)
        raise HTTPException(400, f"Could not parse CSV: {e}")
    return result


@app.get("/receipts/export")
def export_receipts(
    user: models.User = Depends(auth.require_permission("history")),
    db: Session = Depends(database.get_db),
):
    import csv, io
    from fastapi.responses import StreamingResponse

    q = db.query(models.Receipt).order_by(models.Receipt.created_at.desc())
    if not user.is_admin:
        q = q.filter(models.Receipt.user_id == user.id)
    receipts = q.all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["receipt_id", "date", "store", "vendor", "item_name", "category",
                "quantity", "unit_type", "unit_price", "total_price", "vat", "receipt_total", "currency"])
    for r in receipts:
        if r.items:
            for item in r.items:
                w.writerow([r.id, r.receipt_date, r.store_name, r.vendor,
                            item.name, item.category, item.quantity, item.unit_type,
                            item.unit_price, item.total_price, item.vat_applicable,
                            r.total, r.currency])
        else:
            w.writerow([r.id, r.receipt_date, r.store_name, r.vendor,
                        "", "", "", "", "", "", "", r.total, r.currency])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=receipts_export.csv"},
    )


# ── Confirm (user has reviewed, now save) ─────────────────────────────────────
@app.post("/receipts/confirm")
def confirm_receipt(
    payload: dict,
    user: models.User = Depends(auth.require_permission("scan")),
    db: Session = Depends(database.get_db),
):
    """
    Accepts the user-reviewed extraction payload and saves it to the DB.
    payload should be the full pipeline result dict (or just the extracted portion).
    """
    try:
        receipt_id = database.save_receipt(db, payload, user_id=user.id)
        logger.info(f"Confirmed and saved receipt #{receipt_id} for user #{user.id}")
        # Normalize item names in the background (non-blocking)
        import threading
        threading.Thread(target=_normalize_receipt_items, args=(receipt_id,), daemon=True).start()
        return {"receipt_id": receipt_id, "status": "saved"}
    except Exception as e:
        logger.error(f"Confirm save failed: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to save receipt: {e}")


# ── Receipt history ───────────────────────────────────────────────────────────
@app.get("/receipts")
def list_receipts(
    skip: int = 0,
    limit: int = 50,
    user: models.User = Depends(auth.require_permission("history")),
    db: Session = Depends(database.get_db),
):
    q = db.query(models.Receipt).order_by(models.Receipt.created_at.desc())
    if not user.is_admin:
        q = q.filter(models.Receipt.user_id == user.id)
    return [_summary(r) for r in q.offset(skip).limit(limit).all()]


@app.get("/receipts/{receipt_id}")
def get_receipt(
    receipt_id: int,
    user: models.User = Depends(auth.require_permission("history")),
    db: Session = Depends(database.get_db),
):
    r = db.query(models.Receipt).filter(models.Receipt.id == receipt_id).first()
    if not r or (not user.is_admin and r.user_id != user.id):
        raise HTTPException(404, "Receipt not found")
    return _detail(r)


@app.get("/receipts/{receipt_id}/image")
def get_receipt_image(
    receipt_id: int,
    user: models.User = Depends(auth.require_permission("history")),
    db: Session = Depends(database.get_db),
):
    from fastapi.responses import FileResponse
    import mimetypes
    r = db.query(models.Receipt).filter(models.Receipt.id == receipt_id).first()
    if not r or (not user.is_admin and r.user_id != user.id):
        raise HTTPException(404, "Receipt not found")
    if not r.image_path:
        raise HTTPException(404, "No image for this receipt")
    p = Path(r.image_path)
    if not p.exists():
        raise HTTPException(404, "Image file not found on disk")
    mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
    return FileResponse(str(p), media_type=mime)


@app.patch("/receipts/{receipt_id}")
def update_receipt(
    receipt_id: int,
    payload: dict,
    user: models.User = Depends(auth.require_permission("history")),
    db: Session = Depends(database.get_db),
):
    r = db.query(models.Receipt).filter(models.Receipt.id == receipt_id).first()
    if not r or (not user.is_admin and r.user_id != user.id):
        raise HTTPException(404, "Receipt not found")

    for field in ("store_name", "receipt_date", "total", "subtotal", "vat_total", "vendor", "currency"):
        if field in payload:
            setattr(r, field, payload[field] or None)

    if "items" in payload:
        for item in list(r.items):
            db.delete(item)
        db.flush()
        for d in payload["items"]:
            wkg = d.get("weight_kg") or None
            tp  = d.get("total_price")
            per_kg = d.get("per_kg_price") or (round(tp / wkg, 2) if wkg and tp and wkg > 0 else None)
            db.add(models.ReceiptItem(
                receipt_id     = r.id,
                receipt_name   = d.get("receipt_name") or None,
                name           = d.get("name") or d.get("display_name") or "Unknown",
                category       = d.get("category") or None,
                quantity       = float(d.get("quantity") or 1),
                unit_type      = d.get("unit_type") or "unit",
                weight_kg      = wkg,
                unit_price     = d.get("unit_price") or None,
                per_kg_price   = per_kg,
                total_price    = tp or None,
                vat_applicable = bool(d.get("vat_applicable", True)),
                confidence     = d.get("confidence") or None,
                flag           = d.get("flag") or None,
            ))

    db.commit()
    db.refresh(r)
    logger.info(f"Updated receipt #{r.id}")
    if "items" in payload:
        import threading
        threading.Thread(target=_normalize_receipt_items, args=(r.id,), daemon=True).start()
    return _detail(r)


@app.delete("/receipts/{receipt_id}")
def delete_receipt(
    receipt_id: int,
    user: models.User = Depends(auth.require_permission("history")),
    db: Session = Depends(database.get_db),
):
    r = db.query(models.Receipt).filter(models.Receipt.id == receipt_id).first()
    if not r or (not user.is_admin and r.user_id != user.id):
        raise HTTPException(404, "Receipt not found")
    db.delete(r)
    db.commit()
    return {"deleted": receipt_id}


# ── Price search ──────────────────────────────────────────────────────────────

@app.get("/prices/search")
async def price_search(
    q: str = Query(..., min_length=2),
    background_tasks: BackgroundTasks = None,
    user: models.User = Depends(auth.require_permission("prices")),
    db: Session = Depends(database.get_db),
):
    """
    Return cached price results for query `q`. If cache is stale, trigger a
    background scrape so next call returns fresh data.
    """
    if not q.strip():
        raise HTTPException(400, "Query cannot be empty")

    cached = scraper_service.get_cached_results(q, db)
    fresh  = scraper_service.is_cache_fresh(q, db)

    if not fresh and background_tasks is not None:
        background_tasks.add_task(_bg_scrape, q)

    return {
        "query":       q,
        "fresh":       fresh,
        "scraping":    not fresh,
        "results":     cached,
        "store_count": len({r["store"] for r in cached}),
    }


@app.post("/prices/scrape")
async def force_scrape(
    payload: dict,
    user: models.User = Depends(auth.require_permission("prices")),
    db: Session = Depends(database.get_db),
):
    """
    Force an immediate scrape for `query`.
    Pass `store` to scrape a single store; omit to scrape all.
    Returns results in the same format as /prices/search.
    """
    q = (payload.get("query") or "").strip()
    if not q:
        raise HTTPException(400, "query is required")

    store = (payload.get("store") or "").strip() or None
    if store:
        if store not in scraper_service.ONLINE_STORES:
            raise HTTPException(400, f"Unknown store '{store}'. Valid: {scraper_service.ONLINE_STORES}")
        await scraper_service.scrape_store(store, q, db)
        results = scraper_service.get_cached_results(q, db, max_age_hours=1, store=store)
        return {"query": q, "store": store, "count": len(results), "results": results}

    await scraper_service.scrape_all_stores(q, db)
    results = scraper_service.get_cached_results(q, db, max_age_hours=1)
    return {
        "query":   q,
        "results": results,
        "by_store": {
            s: {"count": len([r for r in results if r["store"] == s])}
            for s in scraper_service.ONLINE_STORES
        },
    }


@app.get("/prices/history")
def price_history(
    q: str = Query(..., min_length=2),
    user: models.User = Depends(auth.require_permission("prices")),
    db: Session = Depends(database.get_db),
):
    """All stored price records for a query, regardless of age."""
    listings = (
        db.query(models.StoreListing)
        .filter(models.StoreListing.search_query.ilike(f"%{q.lower()}%"))
        .order_by(models.StoreListing.scraped_at.desc())
        .limit(500)
        .all()
    )
    return [scraper_service._to_dict(l) for l in listings]


@app.get("/prices/receipt-history")
def receipt_price_history(
    ingredient: str = Query(..., min_length=2),
    user: models.User = Depends(auth.require_permission("history")),
    db: Session = Depends(database.get_db),
):
    """
    Find prices for a canonical ingredient from the user's own receipt history.
    Returns each match with store, date, unit_price, and a stale flag if >90 days old.
    """
    cutoff_stale = datetime.now(timezone.utc) - timedelta(days=90)
    q = ingredient.strip().lower()

    rows = (
        db.query(models.ReceiptItem, models.Receipt)
        .join(models.Receipt, models.ReceiptItem.receipt_id == models.Receipt.id)
        .filter(
            models.Receipt.user_id == user.id,
            models.ReceiptItem.canonical_name.isnot(None),
            models.ReceiptItem.canonical_name.ilike(q),
            models.ReceiptItem.total_price.isnot(None),
            models.ReceiptItem.total_price > 0,
        )
        .order_by(models.Receipt.created_at.desc())
        .limit(50)
        .all()
    )

    results = []
    for item, receipt in rows:
        qty = item.quantity or 1
        unit_price = round(item.total_price / qty, 2) if item.total_price else item.unit_price
        stale = receipt.created_at is None or receipt.created_at.replace(tzinfo=timezone.utc) < cutoff_stale
        results.append({
            "canonical_name": item.canonical_name,
            "display_name":   item.name,
            "store":          receipt.store_name,
            "date":           receipt.receipt_date or (receipt.created_at.strftime("%Y-%m-%d") if receipt.created_at else None),
            "unit_price":     unit_price,
            "total_price":    item.total_price,
            "quantity":       qty,
            "currency":       receipt.currency or "ZAR",
            "stale":          stale,
            "receipt_id":     receipt.id,
        })
    return results


@app.post("/admin/import-uitkyk-catalog")
async def admin_import_uitkyk_catalog(
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    """
    Crawl the full Uitkyk catalog (~300 products), normalize all names with
    Claude Haiku, and store in StoreListing.  Existing Uitkyk listings are
    cleared first so prices stay fresh.
    """
    from scrapers.uitkyk import UitkykScraper
    from normalizer import normalize_names

    scraper = UitkykScraper()

    logger.info("Uitkyk catalog import: starting full crawl…")
    products = await scraper.import_full_catalog()

    if not products:
        raise HTTPException(500, "Catalog crawl returned no products")

    # Normalize product names → canonical ingredients (batch of 80 to stay under token limit)
    unique_names = list(dict.fromkeys(p.name for p in products))
    logger.info(f"Uitkyk catalog import: normalizing {len(unique_names)} unique names in batches…")
    mapping: dict[str, str] = {}
    BATCH = 80
    for i in range(0, len(unique_names), BATCH):
        batch = unique_names[i:i + BATCH]
        mapping.update(normalize_names(batch))
        logger.info(f"Uitkyk catalog import: normalized {min(i+BATCH, len(unique_names))}/{len(unique_names)}")

    # Clear old Uitkyk listings and save fresh ones
    db.query(models.StoreListing).filter(models.StoreListing.store == "uitkyk").delete()

    saved = 0
    for product in products:
        canonical = mapping.get(product.name) or product.name
        db.add(models.StoreListing(
            store=product.store,
            store_product_name=product.name,
            search_query=canonical.lower(),
            price=product.price,
            unit_label=product.unit,
            url=product.url,
            image_url=product.image_url,
            in_stock=product.in_stock,
        ))
        saved += 1

    db.commit()
    logger.info(f"Uitkyk catalog import: saved {saved} products")
    return {"imported": saved, "store": "uitkyk"}


@app.post("/admin/normalize-items")
def admin_normalize_items(
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(database.get_db),
):
    """Backfill canonical_name for all existing receipt items that don't have one yet."""
    items = (
        db.query(models.ReceiptItem)
        .filter(models.ReceiptItem.canonical_name.is_(None))
        .all()
    )
    if not items:
        return {"normalized": 0, "message": "All items already normalized"}

    # Group by unique names to minimize Claude calls
    unique_names = list({i.name for i in items})
    logger.info(f"Backfill: normalizing {len(unique_names)} unique names across {len(items)} items")

    # Process in batches of 100
    mapping: dict[str, str] = {}
    BATCH = 100
    for i in range(0, len(unique_names), BATCH):
        batch = unique_names[i:i + BATCH]
        mapping.update(normalize_names(batch))

    for item in items:
        item.canonical_name = mapping.get(item.name) or item.name
    db.commit()
    logger.info(f"Backfill complete: {len(items)} items normalized")
    return {"normalized": len(items), "unique_names": len(unique_names)}


@app.post("/prices/uitkyk/import")
async def import_uitkyk(
    file: UploadFile = File(...),
    user: models.User = Depends(auth.require_permission("prices")),
    db: Session = Depends(database.get_db),
):
    """Import a Uitkyk CSV file to populate store_listings."""
    from scrapers.uitkyk import parse_csv

    content = (await file.read()).decode("utf-8", errors="replace")
    results = parse_csv(content)

    saved = 0
    for r in results:
        db.add(models.StoreListing(
            store=r.store,
            store_product_name=r.name,
            search_query=r.name.lower(),
            price=r.price,
            price_per_kg=r.per_kg_price,
            unit_label=r.unit,
            in_stock=True,
        ))
        saved += 1
    db.commit()
    return {"imported": saved, "store": "uitkyk"}


def _bg_scrape(query: str):
    """Background task: run scrape in a new event loop."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        asyncio.run(scraper_service.scrape_all_stores(query, db))
    except Exception as e:
        logger.error(f"Background scrape failed for '{query}': {e}")
    finally:
        db.close()


# ── Meal planning ──────────────────────────────────────────────────────────────

@app.get("/meals/recipes")
def list_recipes(
    user: models.User = Depends(auth.require_permission("meals")),
    db: Session = Depends(database.get_db),
):
    q = db.query(models.Recipe).order_by(models.Recipe.created_at.desc())
    if not user.is_admin:
        q = q.filter(models.Recipe.user_id == user.id)
    return [_recipe_summary(r) for r in q.all()]


@app.post("/meals/recipes")
def create_recipe(
    payload: dict,
    user: models.User = Depends(auth.require_permission("meals")),
    db: Session = Depends(database.get_db),
):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    recipe = models.Recipe(
        user_id=user.id,
        name=name,
        servings=int(payload.get("servings") or 4),
        notes=payload.get("notes"),
        instructions=payload.get("instructions"),
        source_url=payload.get("source_url"),
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return _recipe_detail(recipe)


@app.post("/meals/recipes/import-url")
async def import_recipe_from_url(
    payload: dict,
    user: models.User = Depends(auth.require_permission("meals")),
    db: Session = Depends(database.get_db),
):
    """
    Fetch a recipe URL, extract schema.org/Recipe markup, and save to DB.
    Returns the created recipe (with all parsed ingredients already saved).
    """
    from recipe_importer import fetch_recipe

    url = (payload.get("url") or "").strip()
    if not url.startswith("http"):
        raise HTTPException(400, "url must be a valid http/https URL")

    try:
        data = await fetch_recipe(url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.error(f"Recipe import error: {e}")
        raise HTTPException(502, f"Could not fetch recipe: {e}")

    recipe = models.Recipe(
        user_id=user.id,
        name=data["name"],
        servings=data["servings"],
        instructions=data["instructions"] or None,
        source_url=data["source_url"],
    )
    db.add(recipe)
    db.flush()

    for ing in data["ingredients"]:
        db.add(models.RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_name=ing["ingredient_name"],
            quantity=ing["quantity"],
            unit=ing["unit"],
            notes=ing.get("notes"),
        ))

    db.commit()
    db.refresh(recipe)
    logger.info(f"Imported recipe '{recipe.name}' ({len(data['ingredients'])} ingredients) from {url}")
    return _recipe_detail(recipe)


@app.get("/meals/recipes/{recipe_id}")
def get_recipe(
    recipe_id: int,
    user: models.User = Depends(auth.require_permission("meals")),
    db: Session = Depends(database.get_db),
):
    r = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not r or (not user.is_admin and r.user_id != user.id):
        raise HTTPException(404, "Recipe not found")
    return _recipe_detail(r)


@app.delete("/meals/recipes/{recipe_id}")
def delete_recipe(
    recipe_id: int,
    user: models.User = Depends(auth.require_permission("meals")),
    db: Session = Depends(database.get_db),
):
    r = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not r or (not user.is_admin and r.user_id != user.id):
        raise HTTPException(404, "Recipe not found")
    db.delete(r)
    db.commit()
    return {"deleted": recipe_id}


@app.post("/meals/recipes/{recipe_id}/ingredients")
def add_ingredient(
    recipe_id: int,
    payload: dict,
    user: models.User = Depends(auth.require_permission("meals")),
    db: Session = Depends(database.get_db),
):
    r = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not r or (not user.is_admin and r.user_id != user.id):
        raise HTTPException(404, "Recipe not found")
    name = (payload.get("ingredient_name") or "").strip()
    if not name:
        raise HTTPException(400, "ingredient_name is required")
    ing = models.RecipeIngredient(
        recipe_id=recipe_id,
        ingredient_name=name,
        quantity=float(payload.get("quantity") or 1),
        unit=payload.get("unit") or "unit",
        notes=payload.get("notes"),
    )
    db.add(ing)
    db.commit()
    db.refresh(ing)
    return _ingredient_dict(ing)


@app.post("/meals/recipes/{recipe_id}/instructions")
def update_instructions(
    recipe_id: int,
    payload: dict,
    user: models.User = Depends(auth.require_permission("meals")),
    db: Session = Depends(database.get_db),
):
    r = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
    if not r or (not user.is_admin and r.user_id != user.id):
        raise HTTPException(404, "Recipe not found")
    r.instructions = payload.get("instructions") or None
    db.commit()
    return {"ok": True}


@app.delete("/meals/ingredients/{ingredient_id}")
def delete_ingredient(
    ingredient_id: int,
    user: models.User = Depends(auth.require_permission("meals")),
    db: Session = Depends(database.get_db),
):
    ing = db.query(models.RecipeIngredient).filter(models.RecipeIngredient.id == ingredient_id).first()
    if not ing:
        raise HTTPException(404, "Ingredient not found")
    if not user.is_admin and ing.recipe.user_id != user.id:
        raise HTTPException(404, "Ingredient not found")
    db.delete(ing)
    db.commit()
    return {"deleted": ingredient_id}


@app.get("/meals/shopping")
def shopping_list(
    recipe_ids: str = Query(...),
    user: models.User = Depends(auth.require_permission("meals")),
    db: Session = Depends(database.get_db),
):
    """
    Generate a shopping list for the given recipe IDs.
    Prices come from two sources (best wins):
      1. User's own receipt history (by canonical_name match)
      2. Scraped store listings
    Prices older than 90 days are flagged as stale.
    """
    ids = [int(x) for x in recipe_ids.split(",") if x.strip().isdigit()]
    if not ids:
        raise HTTPException(400, "recipe_ids must be comma-separated integers")

    recipes = db.query(models.Recipe).filter(models.Recipe.id.in_(ids)).all()
    if not recipes:
        raise HTTPException(404, "No recipes found for given IDs")

    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    # Collect all ingredients
    ingredients = []
    for recipe in recipes:
        for ing in recipe.ingredients:
            ingredients.append({
                "recipe_id":   recipe.id,
                "recipe_name": recipe.name,
                "ingredient":  ing.ingredient_name,
                "quantity":    ing.quantity or 1,
                "unit":        ing.unit,
            })

    result_items = []
    for ing in ingredients:
        query = ing["ingredient"].strip().lower()

        # --- Source 1: receipt history (canonical_name match) ---
        receipt_rows = (
            db.query(models.ReceiptItem, models.Receipt)
            .join(models.Receipt, models.ReceiptItem.receipt_id == models.Receipt.id)
            .filter(
                models.Receipt.user_id == user.id,
                models.ReceiptItem.canonical_name.isnot(None),
                # Exact match OR starts-with (e.g. "Milk" matches "Milk" but not "Milk Tart")
                models.ReceiptItem.canonical_name.ilike(query),
                models.ReceiptItem.total_price.isnot(None),
                models.ReceiptItem.total_price > 0,
            )
            .order_by(models.Receipt.created_at.desc())
            .limit(20)
            .all()
        )

        receipt_prices: dict[str, dict] = {}
        for r_item, receipt in receipt_rows:
            store = receipt.store_name or "Unknown"
            qty = r_item.quantity or 1
            up = round(r_item.total_price / qty, 2)
            stale = (receipt.created_at is None or
                     receipt.created_at.replace(tzinfo=timezone.utc) < stale_cutoff)
            if store not in receipt_prices or up < receipt_prices[store]["price"]:
                receipt_prices[store] = {
                    "store":    store,
                    "price":    up,
                    "date":     receipt.receipt_date or (receipt.created_at.strftime("%Y-%m-%d") if receipt.created_at else None),
                    "stale":    stale,
                    "source":   "receipt",
                    "canonical_name": r_item.canonical_name,
                }

        # --- Source 2: scraped store listings ---
        scraped_rows = (
            db.query(models.StoreListing)
            .filter(
                models.StoreListing.search_query.ilike(f"%{query}%"),
                models.StoreListing.price.isnot(None),
            )
            .order_by(models.StoreListing.price)
            .limit(10)
            .all()
        )

        scraped_prices: dict[str, dict] = {}
        for l in scraped_rows:
            s = l.store
            if s not in scraped_prices:
                d = scraper_service._to_dict(l)
                d["source"] = "scraped"
                d["stale"] = False
                scraped_prices[s] = d

        # Merge: prefer receipt prices; scraped fills gaps
        all_prices = {**scraped_prices, **receipt_prices}

        cheapest = None
        if all_prices:
            cheapest = min(
                all_prices.values(),
                key=lambda x: x.get("price") or float("inf"),
            )

        result_items.append({
            **ing,
            "receipt_prices": list(receipt_prices.values()),
            "scraped_prices": list(scraped_prices.values()),
            "cheapest":       cheapest,
        })

    # Estimated total using cheapest price per ingredient
    estimated_total = sum(
        (item["cheapest"]["price"] or 0) * item["quantity"]
        for item in result_items
        if item["cheapest"] and item["cheapest"].get("price")
    )

    return {
        "recipes":         [{"id": r.id, "name": r.name} for r in recipes],
        "items":           result_items,
        "estimated_total": round(estimated_total, 2),
    }


# ── Households ───────────────────────────────────────────────────────────────

def _hh_member(household_id: int, user_id: int, db: Session):
    return db.query(models.HouseholdMember).filter(
        models.HouseholdMember.household_id == household_id,
        models.HouseholdMember.user_id == user_id,
    ).first()


def _hh_or_404(household_id: int, user: models.User, db: Session):
    hh = db.query(models.Household).filter(models.Household.id == household_id).first()
    if not hh:
        raise HTTPException(404, "Household not found")
    if not user.is_admin and not _hh_member(household_id, user.id, db):
        raise HTTPException(404, "Household not found")
    return hh


def _hh_dict(hh: models.Household, member: models.HouseholdMember | None = None) -> dict:
    return {
        "id":         hh.id,
        "name":       hh.name,
        "created_by": hh.created_by,
        "created_at": hh.created_at.isoformat() if hh.created_at else None,
        "member_count": len(hh.members),
        "my_role":    member.role if member else None,
    }


def _member_dict(m: models.HouseholdMember) -> dict:
    return {
        "user_id":      m.user_id,
        "username":     m.user.username,
        "display_name": m.user.display_name,
        "role":         m.role,
        "joined_at":    m.joined_at.isoformat() if m.joined_at else None,
    }


@app.get("/households")
def list_households(user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    memberships = (
        db.query(models.HouseholdMember)
        .filter(models.HouseholdMember.user_id == user.id)
        .all()
    )
    result = []
    for m in memberships:
        d = _hh_dict(m.household, m)
        result.append(d)
    return result


@app.post("/households")
def create_household(
    payload: dict,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    hh = models.Household(name=name, created_by=user.id)
    db.add(hh)
    db.flush()
    db.add(models.HouseholdMember(household_id=hh.id, user_id=user.id, role="admin"))
    db.commit()
    db.refresh(hh)
    return _hh_dict(hh, _hh_member(hh.id, user.id, db))


@app.get("/households/{household_id}")
def get_household(
    household_id: int,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    hh = _hh_or_404(household_id, user, db)
    me = _hh_member(household_id, user.id, db)

    # Active invite code (visible to admins only)
    invite = None
    if me and me.role == "admin" or user.is_admin:
        now = datetime.now(timezone.utc)
        inv = (
            db.query(models.HouseholdInvite)
            .filter(
                models.HouseholdInvite.household_id == household_id,
                models.HouseholdInvite.is_active == True,  # noqa: E712
                models.HouseholdInvite.expires_at > now,
            )
            .order_by(models.HouseholdInvite.created_at.desc())
            .first()
        )
        if inv:
            invite = {"code": inv.code, "expires_at": inv.expires_at.isoformat()}

    return {
        **_hh_dict(hh, me),
        "members": [_member_dict(m) for m in hh.members],
        "invite":  invite,
    }


@app.patch("/households/{household_id}")
def update_household(
    household_id: int,
    payload: dict,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    hh = _hh_or_404(household_id, user, db)
    me = _hh_member(household_id, user.id, db)
    if not (user.is_admin or (me and me.role == "admin")):
        raise HTTPException(403, "Household admin required")
    name = (payload.get("name") or "").strip()
    if name:
        hh.name = name
    db.commit()
    db.refresh(hh)
    return _hh_dict(hh, me)


@app.delete("/households/{household_id}")
def delete_household(
    household_id: int,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    hh = _hh_or_404(household_id, user, db)
    me = _hh_member(household_id, user.id, db)
    if not (user.is_admin or (me and me.role == "admin")):
        raise HTTPException(403, "Household admin required")
    db.delete(hh)
    db.commit()
    return {"deleted": household_id}


@app.delete("/households/{household_id}/leave")
def leave_household(
    household_id: int,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    me = _hh_member(household_id, user.id, db)
    if not me:
        raise HTTPException(404, "Not a member of this household")
    hh = me.household
    # If the only admin is leaving, block unless they're the last member
    if me.role == "admin":
        other_admins = [m for m in hh.members if m.role == "admin" and m.user_id != user.id]
        other_members = [m for m in hh.members if m.user_id != user.id]
        if other_members and not other_admins:
            raise HTTPException(400, "Assign another admin before leaving")
    db.delete(me)
    # Delete household if now empty
    db.flush()
    remaining = db.query(models.HouseholdMember).filter(
        models.HouseholdMember.household_id == household_id
    ).count()
    if remaining == 0:
        db.delete(hh)
    db.commit()
    return {"left": household_id}


@app.patch("/households/{household_id}/members/{target_user_id}")
def update_member_role(
    household_id: int,
    target_user_id: int,
    payload: dict,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _hh_or_404(household_id, user, db)
    me = _hh_member(household_id, user.id, db)
    if not (user.is_admin or (me and me.role == "admin")):
        raise HTTPException(403, "Household admin required")
    target = _hh_member(household_id, target_user_id, db)
    if not target:
        raise HTTPException(404, "Member not found")
    role = (payload.get("role") or "").strip()
    if role not in ("admin", "member"):
        raise HTTPException(400, "role must be 'admin' or 'member'")
    target.role = role
    db.commit()
    return _member_dict(target)


@app.delete("/households/{household_id}/members/{target_user_id}")
def remove_member(
    household_id: int,
    target_user_id: int,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    hh = _hh_or_404(household_id, user, db)
    me = _hh_member(household_id, user.id, db)
    if not (user.is_admin or (me and me.role == "admin")):
        raise HTTPException(403, "Household admin required")
    if target_user_id == user.id:
        raise HTTPException(400, "Use /leave to leave a household")
    target = _hh_member(household_id, target_user_id, db)
    if not target:
        raise HTTPException(404, "Member not found")
    db.delete(target)
    db.commit()
    return {"removed": target_user_id}


@app.post("/households/{household_id}/invite")
def generate_invite(
    household_id: int,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _hh_or_404(household_id, user, db)
    me = _hh_member(household_id, user.id, db)
    if not (user.is_admin or (me and me.role == "admin")):
        raise HTTPException(403, "Household admin required")

    # Deactivate all existing invites for this household
    db.query(models.HouseholdInvite).filter(
        models.HouseholdInvite.household_id == household_id
    ).update({"is_active": False})

    code = auth.generate_invite_code()
    expires = datetime.now(timezone.utc) + timedelta(hours=auth.INVITE_HOURS)
    inv = models.HouseholdInvite(
        household_id = household_id,
        code         = code,
        created_by   = user.id,
        expires_at   = expires,
        is_active    = True,
    )
    db.add(inv)
    db.commit()
    return {"code": code, "expires_at": expires.isoformat()}


@app.delete("/households/{household_id}/invite")
def deactivate_invite(
    household_id: int,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _hh_or_404(household_id, user, db)
    me = _hh_member(household_id, user.id, db)
    if not (user.is_admin or (me and me.role == "admin")):
        raise HTTPException(403, "Household admin required")
    db.query(models.HouseholdInvite).filter(
        models.HouseholdInvite.household_id == household_id
    ).update({"is_active": False})
    db.commit()
    return {"ok": True}


@app.post("/households/join")
def join_household(
    request: Request,
    payload: dict,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    ip = request.client.host if request.client else "unknown"
    auth.check_join_rate_limit(ip)
    auth.record_join_attempt(ip)

    code = (payload.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(400, "code is required")

    now = datetime.now(timezone.utc)
    inv = db.query(models.HouseholdInvite).filter(
        models.HouseholdInvite.code == code,
        models.HouseholdInvite.is_active == True,  # noqa: E712
        models.HouseholdInvite.expires_at > now,
    ).first()
    if not inv:
        raise HTTPException(404, "Invalid or expired invite code")

    existing = _hh_member(inv.household_id, user.id, db)
    if existing:
        raise HTTPException(409, "Already a member of this household")

    db.add(models.HouseholdMember(
        household_id=inv.household_id, user_id=user.id, role="member"
    ))
    db.commit()
    hh = db.query(models.Household).filter(models.Household.id == inv.household_id).first()
    me = _hh_member(inv.household_id, user.id, db)
    return _hh_dict(hh, me)


@app.get("/households/{household_id}/analytics")
def household_analytics(
    household_id: int,
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    from sqlalchemy import func as sqlfunc
    hh = _hh_or_404(household_id, user, db)
    member_ids = [m.user_id for m in hh.members]
    member_map = {m.user_id: m for m in hh.members}

    rq = db.query(models.Receipt).filter(models.Receipt.user_id.in_(member_ids))
    if from_date:
        rq = rq.filter(models.Receipt.receipt_date >= from_date)
    if to_date:
        rq = rq.filter(models.Receipt.receipt_date <= to_date)

    per_member = rq.with_entities(
        models.Receipt.user_id,
        sqlfunc.count().label("receipt_count"),
        sqlfunc.sum(models.Receipt.total).label("total_spend"),
        sqlfunc.avg(models.Receipt.total).label("avg_per_receipt"),
    ).group_by(models.Receipt.user_id).all()

    by_store = rq.with_entities(
        models.Receipt.store_name,
        sqlfunc.count().label("receipt_count"),
        sqlfunc.sum(models.Receipt.total).label("total"),
    ).group_by(models.Receipt.store_name).order_by(
        sqlfunc.sum(models.Receipt.total).desc()
    ).limit(10).all()

    members_out = []
    total_spend = 0.0
    total_receipts = 0
    for row in per_member:
        m = member_map.get(row.user_id)
        spend = round(float(row.total_spend or 0), 2)
        total_spend += spend
        total_receipts += row.receipt_count
        members_out.append({
            "user_id":        row.user_id,
            "username":       m.user.username if m else str(row.user_id),
            "display_name":   m.user.display_name if m else None,
            "receipt_count":  row.receipt_count,
            "total_spend":    spend,
            "avg_per_receipt": round(float(row.avg_per_receipt or 0), 2),
        })

    # Fill in members with zero receipts
    represented = {r.user_id for r in per_member}
    for uid, m in member_map.items():
        if uid not in represented:
            members_out.append({
                "user_id":        uid,
                "username":       m.user.username,
                "display_name":   m.user.display_name,
                "receipt_count":  0,
                "total_spend":    0.0,
                "avg_per_receipt": 0.0,
            })

    members_out.sort(key=lambda x: x["total_spend"], reverse=True)

    return {
        "household":   _hh_dict(hh, _hh_member(household_id, user.id, db)),
        "members":     members_out,
        "totals": {
            "receipt_count":    total_receipts,
            "total_spend":      round(total_spend, 2),
            "member_count":     len(hh.members),
            "avg_per_member":   round(total_spend / len(hh.members), 2) if hh.members else 0,
        },
        "by_store": [
            {"store": r.store_name or "Unknown", "receipt_count": r.receipt_count,
             "total": round(float(r.total or 0), 2)}
            for r in by_store
        ],
    }


@app.get("/households/{household_id}/history")
def household_history(
    household_id: int,
    skip: int = 0,
    limit: int = 50,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    hh = _hh_or_404(household_id, user, db)
    member_ids = [m.user_id for m in hh.members]
    member_map = {m.user_id: m for m in hh.members}

    receipts = (
        db.query(models.Receipt)
        .filter(models.Receipt.user_id.in_(member_ids))
        .order_by(models.Receipt.created_at.desc())
        .offset(skip).limit(limit).all()
    )
    total = db.query(models.Receipt).filter(models.Receipt.user_id.in_(member_ids)).count()

    out = []
    for r in receipts:
        m = member_map.get(r.user_id)
        out.append({
            **_summary(r),
            "member_username":     m.user.username if m else None,
            "member_display_name": m.user.display_name if m else None,
        })
    return {"receipts": out, "total": total}


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/analytics/stores")
def analytics_stores(
    user: models.User = Depends(auth.require_permission("analytics")),
    db: Session = Depends(database.get_db),
):
    q = db.query(models.Receipt.store_name).filter(models.Receipt.store_name.isnot(None))
    if not user.is_admin:
        q = q.filter(models.Receipt.user_id == user.id)
    names = sorted({row[0] for row in q.distinct().all() if row[0]})
    return {"stores": names}


@app.get("/analytics/items")
def analytics_items(
    q: str = Query(default=""),
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    store: Optional[str] = Query(default=None),
    user: models.User = Depends(auth.require_permission("analytics")),
    db: Session = Depends(database.get_db),
):
    from sqlalchemy import func, desc

    base = db.query(models.ReceiptItem).join(models.Receipt)
    if not user.is_admin:
        base = base.filter(models.Receipt.user_id == user.id)
    if q:
        base = base.filter(models.ReceiptItem.name.ilike(f"%{q}%"))
    if from_date:
        base = base.filter(models.Receipt.receipt_date >= from_date)
    if to_date:
        base = base.filter(models.Receipt.receipt_date <= to_date)
    if category:
        base = base.filter(models.ReceiptItem.category == category)
    if store:
        base = base.filter(models.Receipt.store_name == store)

    stats = base.with_entities(
        func.count().label("count"),
        func.sum(models.ReceiptItem.total_price).label("total_spend"),
        func.avg(models.ReceiptItem.unit_price).label("avg_price"),
        func.min(models.ReceiptItem.unit_price).label("min_price"),
        func.max(models.ReceiptItem.unit_price).label("max_price"),
    ).first()

    by_store = base.with_entities(
        models.Receipt.store_name,
        func.count().label("count"),
        func.sum(models.ReceiptItem.total_price).label("total"),
        func.avg(models.ReceiptItem.unit_price).label("avg_price"),
    ).group_by(models.Receipt.store_name).order_by(
        desc(func.sum(models.ReceiptItem.total_price))
    ).all()

    history = base.with_entities(
        models.Receipt.receipt_date,
        models.Receipt.store_name,
        models.ReceiptItem.name,
        models.ReceiptItem.quantity,
        models.ReceiptItem.unit_price,
        models.ReceiptItem.total_price,
    ).order_by(models.Receipt.receipt_date.desc()).limit(200).all()

    return {
        "query": q,
        "stats": {
            "count":      stats.count or 0,
            "total_spend": round(float(stats.total_spend or 0), 2),
            "avg_price":  round(float(stats.avg_price or 0), 2),
            "min_price":  round(float(stats.min_price or 0), 2),
            "max_price":  round(float(stats.max_price or 0), 2),
        },
        "by_store": [
            {
                "store":     row.store_name or "Unknown",
                "count":     row.count,
                "total":     round(float(row.total or 0), 2),
                "avg_price": round(float(row.avg_price or 0), 2),
            }
            for row in by_store
        ],
        "history": [
            {
                "date":        row.receipt_date,
                "store":       row.store_name or "Unknown",
                "name":        row.name,
                "quantity":    row.quantity,
                "unit_price":  row.unit_price,
                "total_price": row.total_price,
            }
            for row in history
        ],
    }


@app.get("/analytics/summary")
def analytics_summary(
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
    store: Optional[str] = Query(default=None),
    user: models.User = Depends(auth.require_permission("analytics")),
    db: Session = Depends(database.get_db),
):
    from sqlalchemy import func, desc

    receipt_q = db.query(models.Receipt)
    item_q    = db.query(models.ReceiptItem).join(models.Receipt)
    if not user.is_admin:
        receipt_q = receipt_q.filter(models.Receipt.user_id == user.id)
        item_q    = item_q.filter(models.Receipt.user_id == user.id)
    if from_date:
        receipt_q = receipt_q.filter(models.Receipt.receipt_date >= from_date)
        item_q    = item_q.filter(models.Receipt.receipt_date >= from_date)
    if to_date:
        receipt_q = receipt_q.filter(models.Receipt.receipt_date <= to_date)
        item_q    = item_q.filter(models.Receipt.receipt_date <= to_date)
    if store:
        receipt_q = receipt_q.filter(models.Receipt.store_name == store)
        item_q    = item_q.filter(models.Receipt.store_name == store)

    total_receipts = receipt_q.count()
    total_spend    = receipt_q.with_entities(func.sum(models.Receipt.total)).scalar()

    by_cat = item_q.with_entities(
        models.ReceiptItem.category,
        func.count().label("count"),
        func.sum(models.ReceiptItem.total_price).label("total"),
    ).group_by(models.ReceiptItem.category).order_by(
        desc(func.sum(models.ReceiptItem.total_price))
    ).all()

    by_store = receipt_q.with_entities(
        models.Receipt.store_name,
        func.count().label("receipt_count"),
        func.sum(models.Receipt.total).label("total"),
    ).group_by(models.Receipt.store_name).order_by(
        desc(func.sum(models.Receipt.total))
    ).all()

    top_items = item_q.with_entities(
        models.ReceiptItem.name,
        func.count().label("count"),
        func.sum(models.ReceiptItem.total_price).label("total"),
        func.avg(models.ReceiptItem.unit_price).label("avg_price"),
    ).group_by(models.ReceiptItem.name).order_by(desc(func.count())).limit(25).all()

    return {
        "overview": {
            "total_receipts": total_receipts,
            "total_spend":    round(float(total_spend or 0), 2),
        },
        "by_category": [
            {"category": r.category or "uncategorised", "count": r.count, "total": round(float(r.total or 0), 2)}
            for r in by_cat
        ],
        "by_store": [
            {"store": r.store_name or "Unknown", "receipt_count": r.receipt_count, "total": round(float(r.total or 0), 2)}
            for r in by_store
        ],
        "top_items": [
            {"name": r.name, "count": r.count, "total": round(float(r.total or 0), 2), "avg_price": round(float(r.avg_price or 0), 2)}
            for r in top_items
        ],
    }


@app.get("/analytics", response_class=HTMLResponse, include_in_schema=False)
def analytics_page(request: Request, db: Session = Depends(database.get_db)):
    return _html(request, db, "analytics.html")


@app.get("/household", response_class=HTMLResponse, include_in_schema=False)
def household_page(request: Request, db: Session = Depends(database.get_db)):
    return _html(request, db, "household.html")


@app.get("/spend-groups", response_class=HTMLResponse, include_in_schema=False)
def spend_groups_page(request: Request, db: Session = Depends(database.get_db)):
    return _html(request, db, "spend-groups.html")


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_page(request: Request, db: Session = Depends(database.get_db)):
    user = _session_user(request, db)
    if not user:
        return RedirectResponse(f"/login?next=/admin", status_code=303)
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return (Path("static") / "admin.html").read_text()


# ── Spend groups ──────────────────────────────────────────────────────────────

def _sg_member(group_id: int, user_id: int, db: Session):
    return db.query(models.SpendGroupMember).filter(
        models.SpendGroupMember.group_id == group_id,
        models.SpendGroupMember.user_id == user_id,
    ).first()


def _sg_or_404(group_id: int, user: models.User, db: Session):
    g = db.query(models.SpendGroup).filter(models.SpendGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Spend group not found")
    if not user.is_admin and not _sg_member(group_id, user.id, db):
        raise HTTPException(404, "Spend group not found")
    return g


def _sg_dict(g: models.SpendGroup, user_id: int | None = None) -> dict:
    my_role = None
    if user_id:
        if g.user_id == user_id:
            my_role = "owner"
        elif any(m.user_id == user_id for m in g.members):
            my_role = "member"
    return {
        "id":          g.id,
        "name":        g.name,
        "color":       g.color,
        "is_personal": g.is_personal,
        "created_by":  g.user_id,
        "member_count": len(g.members),
        "my_role":     my_role,
        "created_at":  g.created_at.isoformat() if g.created_at else None,
    }


@app.get("/api/spend-groups")
def list_spend_groups(
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    memberships = db.query(models.SpendGroupMember).filter(
        models.SpendGroupMember.user_id == user.id
    ).all()
    group_ids = [m.group_id for m in memberships]
    groups = db.query(models.SpendGroup).filter(models.SpendGroup.id.in_(group_ids)).order_by(models.SpendGroup.created_at).all()
    return [_sg_dict(g, user.id) for g in groups]


@app.post("/api/spend-groups")
def create_spend_group(
    payload: dict,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    color       = (payload.get("color") or "#6366f1").strip()
    is_personal = bool(payload.get("is_personal", False))
    g = models.SpendGroup(user_id=user.id, name=name, color=color, is_personal=is_personal)
    db.add(g)
    db.flush()
    db.add(models.SpendGroupMember(group_id=g.id, user_id=user.id))
    db.commit()
    db.refresh(g)
    return _sg_dict(g, user.id)


@app.get("/api/spend-groups/{group_id}")
def get_spend_group(
    group_id: int,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    g = _sg_or_404(group_id, user, db)
    return {
        **_sg_dict(g, user.id),
        "members": [
            {
                "user_id":      m.user_id,
                "username":     m.user.username,
                "display_name": m.user.display_name,
                "is_owner":     m.user_id == g.user_id,
                "joined_at":    m.joined_at.isoformat() if m.joined_at else None,
            }
            for m in g.members
        ],
    }


@app.patch("/api/spend-groups/{group_id}")
def update_spend_group(
    group_id: int,
    payload: dict,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    g = _sg_or_404(group_id, user, db)
    if g.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "Only the group owner can modify it")
    if "name" in payload:
        name = (payload["name"] or "").strip()
        if name:
            g.name = name
    if "color" in payload:
        g.color = (payload["color"] or "#6366f1").strip()
    if "is_personal" in payload:
        g.is_personal = bool(payload["is_personal"])
    db.commit()
    db.refresh(g)
    return _sg_dict(g, user.id)


@app.delete("/api/spend-groups/{group_id}")
def delete_spend_group(
    group_id: int,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    g = _sg_or_404(group_id, user, db)
    if g.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "Only the group owner can delete it")
    db.delete(g)
    db.commit()
    return {"deleted": group_id}


@app.post("/api/spend-groups/{group_id}/members")
def add_spend_group_member(
    group_id: int,
    payload: dict,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    g = _sg_or_404(group_id, user, db)
    if g.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "Only the group owner can add members")
    from sqlalchemy import func as sqlfunc
    username = (payload.get("username") or "").strip().lower()
    if not username:
        raise HTTPException(400, "username is required")
    target = db.query(models.User).filter(sqlfunc.lower(models.User.username) == username).first()
    if not target or not target.is_active:
        raise HTTPException(404, f"User '{username}' not found")
    if _sg_member(group_id, target.id, db):
        raise HTTPException(409, "Already a member")
    db.add(models.SpendGroupMember(group_id=group_id, user_id=target.id))
    db.commit()
    db.refresh(g)
    return {
        "user_id":      target.id,
        "username":     target.username,
        "display_name": target.display_name,
        "is_owner":     False,
    }


@app.delete("/api/spend-groups/{group_id}/members/{target_uid}")
def remove_spend_group_member(
    group_id: int,
    target_uid: int,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    g = _sg_or_404(group_id, user, db)
    if g.user_id != user.id and not user.is_admin and user.id != target_uid:
        raise HTTPException(403, "Insufficient permissions")
    if target_uid == g.user_id:
        raise HTTPException(400, "Cannot remove the group owner")
    m = _sg_member(group_id, target_uid, db)
    if not m:
        raise HTTPException(404, "Member not found")
    db.delete(m)
    db.commit()
    return {"removed": target_uid}


@app.get("/api/spend-groups/{group_id}/balance")
def spend_group_balance(
    group_id: int,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    g = _sg_or_404(group_id, user, db)
    member_ids = {m.user_id for m in g.members}
    member_map = {m.user_id: m for m in g.members}

    # All item tags for this group where the payer (receipt.user_id) is a member
    rows = (
        db.query(models.ReceiptItemTag, models.ReceiptItem, models.Receipt)
        .join(models.ReceiptItem, models.ReceiptItemTag.item_id == models.ReceiptItem.id)
        .join(models.Receipt,     models.ReceiptItem.receipt_id == models.Receipt.id)
        .filter(models.ReceiptItemTag.spend_group_id == group_id)
        .filter(models.Receipt.user_id.in_(member_ids))
        .all()
    )

    paid_by: dict[int, float] = {uid: 0.0 for uid in member_ids}
    for tag, item, receipt in rows:
        paid_by[receipt.user_id] += item.total_price or 0.0

    total      = sum(paid_by.values())
    n          = len(member_ids)
    fair_share = total / n if n > 0 else 0.0

    members_out = []
    for uid in member_ids:
        m    = member_map[uid]
        paid = paid_by.get(uid, 0.0)
        members_out.append({
            "user_id":      uid,
            "username":     m.user.username,
            "display_name": m.user.display_name,
            "paid":         round(paid, 2),
            "fair_share":   round(fair_share, 2),
            "balance":      round(paid - fair_share, 2),
        })
    members_out.sort(key=lambda x: x["balance"], reverse=True)

    # Minimal settlement: match creditors to debtors
    creditors = [[d["user_id"], d["username"], d["balance"]]  for d in members_out if d["balance"] >  0.005]
    debtors   = [[d["user_id"], d["username"], -d["balance"]] for d in members_out if d["balance"] < -0.005]
    settlements, ci, di = [], 0, 0
    while ci < len(creditors) and di < len(debtors):
        c_uid, c_name, c_amt = creditors[ci]
        d_uid, d_name, d_amt = debtors[di]
        transfer = min(c_amt, d_amt)
        settlements.append({
            "from_user_id": d_uid, "from": d_name,
            "to_user_id":   c_uid, "to":   c_name,
            "amount":       round(transfer, 2),
        })
        creditors[ci][2] -= transfer
        debtors[di][2]   -= transfer
        if creditors[ci][2] < 0.005:
            ci += 1
        if debtors[di][2] < 0.005:
            di += 1

    return {
        "group":        _sg_dict(g, user.id),
        "total_tagged": round(total, 2),
        "fair_share":   round(fair_share, 2),
        "members":      members_out,
        "settlements":  settlements,
    }


@app.put("/receipts/{receipt_id}/items/{item_id}/tags")
def set_item_tags(
    receipt_id: int,
    item_id: int,
    payload: dict,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    r = db.query(models.Receipt).filter(models.Receipt.id == receipt_id).first()
    if not r or (not user.is_admin and r.user_id != user.id):
        raise HTTPException(404, "Receipt not found")
    item = db.query(models.ReceiptItem).filter(
        models.ReceiptItem.id == item_id,
        models.ReceiptItem.receipt_id == receipt_id,
    ).first()
    if not item:
        raise HTTPException(404, "Item not found")

    group_ids = [int(gid) for gid in (payload.get("group_ids") or [])]
    if group_ids:
        valid = {m.group_id for m in db.query(models.SpendGroupMember).filter(
            models.SpendGroupMember.user_id == user.id,
            models.SpendGroupMember.group_id.in_(group_ids),
        ).all()}
        bad = [gid for gid in group_ids if gid not in valid]
        if bad:
            raise HTTPException(400, f"Not a member of groups: {bad}")

    db.query(models.ReceiptItemTag).filter(models.ReceiptItemTag.item_id == item_id).delete()
    for gid in group_ids:
        db.add(models.ReceiptItemTag(item_id=item_id, spend_group_id=gid, tagged_by=user.id))
    db.commit()
    return {"item_id": item_id, "group_ids": group_ids}


def _recipe_summary(r: models.Recipe) -> dict:
    return {
        "id":               r.id,
        "name":             r.name,
        "servings":         r.servings,
        "ingredient_count": len(r.ingredients),
        "source_url":       r.source_url,
        "created_at":       r.created_at.isoformat() if r.created_at else None,
    }


def _recipe_detail(r: models.Recipe) -> dict:
    return {
        **_recipe_summary(r),
        "notes":        r.notes,
        "instructions": r.instructions,
        "ingredients":  [_ingredient_dict(i) for i in r.ingredients],
    }


def _ingredient_dict(i: models.RecipeIngredient) -> dict:
    return {
        "id":              i.id,
        "ingredient_name": i.ingredient_name,
        "quantity":        i.quantity,
        "unit":            i.unit,
        "notes":           i.notes,
    }


# ── Serialisation ─────────────────────────────────────────────────────────────
def _normalize_receipt_items(receipt_id: int):
    """Background task: call Claude Haiku to fill canonical_name for all items on a receipt."""
    db = database.SessionLocal()
    try:
        items = db.query(models.ReceiptItem).filter(models.ReceiptItem.receipt_id == receipt_id).all()
        if not items:
            return
        names = [i.name for i in items]
        mapping = normalize_names(names)
        for item in items:
            item.canonical_name = mapping.get(item.name) or item.name
        db.commit()
        logger.info(f"Normalized {len(items)} items for receipt #{receipt_id}")
    except Exception as e:
        logger.error(f"Normalization failed for receipt #{receipt_id}: {e}")
    finally:
        db.close()


def _user_dict(u: models.User) -> dict:
    return {
        "id":             u.id,
        "username":       u.username,
        "email":          u.email,
        "email_verified": u.email_verified,
        "display_name":   u.display_name,
        "is_admin":       u.is_admin,
        "is_active":      u.is_active,
        "permissions":    u.permissions or [],
        "created_at":     u.created_at.isoformat() if u.created_at else None,
    }


def _reg_dict(r: models.RegistrationRequest) -> dict:
    return {
        "id":             r.id,
        "username":       r.username,
        "email":          r.email,
        "display_name":   r.display_name,
        "email_verified": r.email_verified,
        "status":         r.status,
        "denial_reason":  r.denial_reason,
        "created_at":     r.created_at.isoformat() if r.created_at else None,
        "reviewed_at":    r.reviewed_at.isoformat() if r.reviewed_at else None,
    }


def _summary(r):
    return {
        "id": r.id, "store": r.store_name, "vendor": r.vendor,
        "date": r.receipt_date, "total": r.total, "currency": r.currency,
        "item_count": len(r.items),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }

def _detail(r):
    return {
        **_summary(r),
        "subtotal": r.subtotal, "vat_total": r.vat_total,
        "store_conf": r.store_conf, "date_conf": r.date_conf,
        "tax_groups": r.tax_groups,
        "items": [
            {
                "id":             i.id,
                "receipt_name":   i.receipt_name,
                "name":           i.name,
                "canonical_name": i.canonical_name,
                "category":       i.category,
                "quantity":       i.quantity,
                "unit_type":      i.unit_type,
                "weight_kg":      i.weight_kg,
                "unit_price":     i.unit_price,
                "per_kg_price":   i.per_kg_price,
                "total_price":    i.total_price,
                "vat_applicable": i.vat_applicable,
                "confidence":     i.confidence,
                "flag":           i.flag,
                "spend_group_ids": [t.spend_group_id for t in i.tags],
            }
            for i in r.items
        ],
    }
