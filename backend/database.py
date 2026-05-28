import logging
import os
import secrets
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger("database")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://receipt:receipt@db:5432/receipts")

engine       = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


def init_db():
    import models  # noqa
    Base.metadata.create_all(bind=engine)
    _migrate()
    ensure_admin_exists()


def _migrate():
    """Safe idempotent column additions for schema evolution."""
    new_columns = [
        ("receipts",      "vendor",        "VARCHAR"),
        ("receipts",      "tax_groups",    "JSONB"),
        ("receipts",      "user_id",       "INTEGER REFERENCES users(id)"),
        ("receipt_items", "receipt_name",  "VARCHAR"),
        ("receipt_items", "category",      "VARCHAR"),
        ("receipt_items", "weight_kg",     "FLOAT"),
        ("receipt_items", "per_kg_price",  "FLOAT"),
        ("recipes",       "instructions",  "TEXT"),
        ("recipes",       "source_url",    "VARCHAR"),
        ("recipes",       "user_id",       "INTEGER REFERENCES users(id)"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in new_columns:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
                conn.commit()
            except Exception:
                conn.rollback()

        # Normalise all existing usernames to lowercase
        try:
            conn.execute(text("UPDATE users SET username = LOWER(username) WHERE username != LOWER(username)"))
            conn.commit()
        except Exception:
            conn.rollback()


def ensure_admin_exists():
    from models import User
    from auth import hash_password

    db = SessionLocal()
    try:
        if db.query(User).filter(User.is_admin == True).count() > 0:  # noqa: E712
            return

        username = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
        password = os.getenv("ADMIN_PASSWORD", "")
        if not password:
            password = secrets.token_urlsafe(16)
            logger.warning(
                "\n" + "=" * 60 +
                f"\n  ADMIN ACCOUNT CREATED\n"
                f"  Username : {username}\n"
                f"  Password : {password}\n"
                f"  CHANGE THIS IMMEDIATELY!\n" +
                "=" * 60
            )

        admin = User(
            username      = username,
            display_name  = "Administrator",
            password_hash = hash_password(password),
            is_admin      = True,
            is_active     = True,
            permissions   = [],
        )
        db.add(admin)
        db.commit()
        logger.info(f"Admin account '{username}' created.")
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_receipt(db, payload: dict, image_path: str | None = None, user_id: int | None = None) -> int:
    """
    Persist a confirmed receipt payload to the database.
    payload is the user-reviewed 'extracted' dict plus image_path and vendor.
    Returns the new receipt id.
    """
    from models import Receipt, ReceiptItem

    ext   = payload.get("extracted", payload)  # accept both wrapped and unwrapped
    store = ext.get("store", {})
    date  = ext.get("date",  {})

    receipt = Receipt(
        user_id      = user_id,
        image_path   = image_path or payload.get("image_path"),
        store_name   = store.get("name"),
        store_conf   = store.get("confidence"),
        receipt_date = date.get("value"),
        date_conf    = date.get("confidence"),
        vendor       = payload.get("vendor"),
        subtotal     = ext.get("subtotal"),
        vat_total    = ext.get("vat_total"),
        total        = ext.get("total"),
        currency     = ext.get("currency", "ZAR"),
        tax_groups   = ext.get("tax_groups"),
    )
    db.add(receipt)
    db.flush()

    for item_data in ext.get("items", []):
        display = item_data.get("display_name") or item_data.get("name") or "Unknown"

        # Calculate per_kg_price if not provided but weight_kg and total_price are known
        per_kg = item_data.get("per_kg_price")
        if per_kg is None:
            wkg = item_data.get("weight_kg")
            tot = item_data.get("total_price")
            if wkg and tot and wkg > 0:
                per_kg = round(tot / wkg, 2)

        item = ReceiptItem(
            receipt_id     = receipt.id,
            receipt_name   = item_data.get("receipt_name"),
            name           = display,
            category       = item_data.get("category"),
            quantity       = item_data.get("quantity", 1),
            unit_type      = item_data.get("unit_type", "unit"),
            weight_kg      = item_data.get("weight_kg"),
            unit_price     = item_data.get("unit_price"),
            per_kg_price   = per_kg,
            total_price    = item_data.get("total_price"),
            vat_applicable = item_data.get("vat_applicable", True),
            confidence     = item_data.get("confidence"),
            flag           = item_data.get("flag"),
        )
        db.add(item)

    db.commit()
    return receipt.id
