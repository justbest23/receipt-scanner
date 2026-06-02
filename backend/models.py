from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


# ── Auth models ────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    username       = Column(String, unique=True, nullable=False, index=True)
    email          = Column(String, unique=True, nullable=True, index=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    display_name   = Column(String, nullable=True)
    password_hash  = Column(String, nullable=False)
    is_admin       = Column(Boolean, default=False, nullable=False)
    is_active      = Column(Boolean, default=True, nullable=False)
    permissions    = Column(JSON, default=list)
    currency       = Column(String, default="ZAR")
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    receipts = relationship("Receipt", back_populates="user")
    recipes  = relationship("Recipe",  back_populates="user")


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"

    id             = Column(Integer, primary_key=True, index=True)
    username       = Column(String, nullable=False)
    email          = Column(String, nullable=False, index=True)
    display_name   = Column(String, nullable=True)
    password_hash  = Column(String, nullable=False)
    email_token    = Column(String, unique=True, nullable=False, index=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    # pending_email → pending_admin → approved | denied
    status         = Column(String, default="pending_email", nullable=False)
    denial_reason  = Column(String, nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at    = Column(DateTime(timezone=True), nullable=True)
    reviewed_by    = Column(Integer, ForeignKey("users.id"), nullable=True)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    token      = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="sessions")


# ── Receipt models ─────────────────────────────────────────────────────────────


class Receipt(Base):
    __tablename__ = "receipts"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    image_path   = Column(String, nullable=True)
    store_name   = Column(String, nullable=True)
    store_conf   = Column(Float, nullable=True)
    receipt_date = Column(String, nullable=True)
    date_conf    = Column(Float, nullable=True)
    vendor       = Column(String, nullable=True)   # detected vendor name
    subtotal     = Column(Float, nullable=True)
    vat_total    = Column(Float, nullable=True)
    total        = Column(Float, nullable=True)
    currency     = Column(String, default="ZAR")
    tax_groups   = Column(JSON, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    user  = relationship("User", back_populates="receipts")
    items = relationship("ReceiptItem", back_populates="receipt", cascade="all, delete-orphan")


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id             = Column(Integer, primary_key=True, index=True)
    receipt_id     = Column(Integer, ForeignKey("receipts.id"), nullable=False)
    receipt_name   = Column(String, nullable=True)   # raw text from receipt
    name           = Column(String, nullable=False)  # decoded display name
    canonical_name = Column(String, nullable=True)   # generic ingredient (no brand/size)
    category       = Column(String, nullable=True)
    quantity       = Column(Float, default=1.0)
    unit_type      = Column(String, default="unit")  # unit | weight_kg | weight_g
    weight_kg      = Column(Float, nullable=True)    # actual weight if known
    unit_price     = Column(Float, nullable=True)
    per_kg_price   = Column(Float, nullable=True)    # calculated or extracted per-kg price
    total_price    = Column(Float, nullable=True)
    vat_applicable = Column(Boolean, default=True)
    confidence     = Column(Float, nullable=True)
    flag           = Column(String, nullable=True)

    receipt = relationship("Receipt", back_populates="items")
    tags    = relationship("ReceiptItemTag", back_populates="item", cascade="all, delete-orphan")


# ── Price tracking models ──────────────────────────────────────────────────────

class Product(Base):
    __tablename__ = "products"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False, index=True)
    category   = Column(String, nullable=True)
    unit_type  = Column(String, default="unit")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    listings   = relationship("StoreListing", back_populates="product")


class StoreListing(Base):
    __tablename__ = "store_listings"

    id                 = Column(Integer, primary_key=True, index=True)
    product_id         = Column(Integer, ForeignKey("products.id"), nullable=True)
    store              = Column(String, nullable=False, index=True)
    store_product_name = Column(String, nullable=False)
    search_query       = Column(String, nullable=True, index=True)
    price              = Column(Float, nullable=True)
    price_per_kg       = Column(Float, nullable=True)
    unit_label         = Column(String, nullable=True)
    url                = Column(String, nullable=True)
    image_url          = Column(String, nullable=True)
    in_stock           = Column(Boolean, default=True)
    scraped_at         = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="listings")


# ── Household models ───────────────────────────────────────────────────────────

class Household(Base):
    __tablename__ = "households"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("HouseholdMember", back_populates="household", cascade="all, delete-orphan")
    invites = relationship("HouseholdInvite", back_populates="household", cascade="all, delete-orphan")


class HouseholdMember(Base):
    __tablename__ = "household_members"

    id           = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id"), nullable=False)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    role         = Column(String, default="member")  # "admin" | "member"
    joined_at    = Column(DateTime(timezone=True), server_default=func.now())

    household = relationship("Household", back_populates="members")
    user      = relationship("User")


class HouseholdInvite(Base):
    __tablename__ = "household_invites"

    id           = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id"), nullable=False)
    code         = Column(String, unique=True, nullable=False, index=True)
    created_by   = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at   = Column(DateTime(timezone=True), nullable=False)
    is_active    = Column(Boolean, default=True, nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    household = relationship("Household", back_populates="invites")


# ── Spend group models ────────────────────────────────────────────────────────

class SpendGroup(Base):
    __tablename__ = "spend_groups"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    name        = Column(String, nullable=False)
    color       = Column(String, default="#6366f1")
    is_personal = Column(Boolean, default=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    members   = relationship("SpendGroupMember", back_populates="group", cascade="all, delete-orphan")
    item_tags = relationship("ReceiptItemTag",   back_populates="group", cascade="all, delete-orphan")


class SpendGroupMember(Base):
    __tablename__ = "spend_group_members"

    id        = Column(Integer, primary_key=True, index=True)
    group_id  = Column(Integer, ForeignKey("spend_groups.id"), nullable=False)
    user_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("SpendGroup", back_populates="members")
    user  = relationship("User")


class ReceiptItemTag(Base):
    __tablename__ = "receipt_item_tags"

    id             = Column(Integer, primary_key=True, index=True)
    item_id        = Column(Integer, ForeignKey("receipt_items.id"), nullable=False)
    spend_group_id = Column(Integer, ForeignKey("spend_groups.id"), nullable=False)
    tagged_by      = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    group  = relationship("SpendGroup", back_populates="item_tags")
    item   = relationship("ReceiptItem", back_populates="tags")
    tagger = relationship("User")


# ── Meal planning models ───────────────────────────────────────────────────────

class Recipe(Base):
    __tablename__ = "recipes"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name         = Column(String, nullable=False)
    servings     = Column(Integer, default=4)
    notes        = Column(Text, nullable=True)
    instructions = Column(Text, nullable=True)   # full method / steps
    source_url   = Column(String, nullable=True) # original recipe URL
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    user        = relationship("User", back_populates="recipes")
    ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id              = Column(Integer, primary_key=True, index=True)
    recipe_id       = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    ingredient_name = Column(String, nullable=False)
    quantity        = Column(Float, default=1.0)
    unit            = Column(String, default="unit")
    notes           = Column(String, nullable=True)

    recipe = relationship("Recipe", back_populates="ingredients")


# ── Normalization corrections ──────────────────────────────────────────────────

class NormalizationCorrection(Base):
    __tablename__ = "normalization_corrections"

    id            = Column(Integer, primary_key=True, index=True)
    raw_name      = Column(String, nullable=False, unique=True, index=True)
    canonical     = Column(String, nullable=False)
    corrected_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
