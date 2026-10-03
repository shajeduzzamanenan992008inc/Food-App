from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer", index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    preferred_locale = db.Column(db.String(12), nullable=True)
    auth_version = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    password_reset_hash = db.Column(db.String(64), nullable=True)
    password_reset_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    password_reset_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    password_reset_attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    __table_args__ = (
        db.CheckConstraint("role IN ('customer', 'seller', 'rider', 'admin')", name="ck_user_role_valid"),
        db.CheckConstraint("auth_version >= 0", name="ck_user_auth_version_nonnegative"),
        db.CheckConstraint(
            "password_reset_attempts >= 0", name="ck_user_password_reset_attempts_nonnegative"
        ),
    )

    customer_profile = db.relationship(
        "CustomerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    admin_profile = db.relationship(
        "AdminProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    seller_profile = db.relationship(
        "SellerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan",
        foreign_keys="SellerProfile.user_id",
    )
    rider_profile = db.relationship(
        "RiderProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    orders = db.relationship(
        "Order", backref="user", lazy="dynamic", foreign_keys="Order.user_id", passive_deletes=True
    )
    notifications = db.relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan",
        order_by="Notification.created_at.desc()",
    )
    wishlist_items = db.relationship(
        "WishlistItem", back_populates="user", cascade="all, delete-orphan",
        order_by="WishlistItem.created_at.desc()",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class CustomerProfile(TimestampMixin, db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    profile_image = db.Column(db.String(255), nullable=True)

    user = db.relationship("User", back_populates="customer_profile")
    address = db.relationship(
        "CustomerAddress", back_populates="customer", uselist=False, cascade="all, delete-orphan"
    )


class CustomerAddress(TimestampMixin, db.Model):
    __tablename__ = "addresses"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="CASCADE"), unique=True, nullable=False)
    address_line = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(100), nullable=False)

    customer = db.relationship("CustomerProfile", back_populates="address")


class AdminProfile(TimestampMixin, db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    profile_image = db.Column(db.String(255), nullable=True)

    user = db.relationship("User", back_populates="admin_profile")


class SellerProfile(TimestampMixin, db.Model):
    __tablename__ = "seller_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    store_name = db.Column(db.String(120), nullable=False)
    contact_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    business_address = db.Column(db.String(500), nullable=True)
    approval_status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_note = db.Column(db.String(500), nullable=True)
    __table_args__ = (
        db.CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected', 'suspended')",
            name="ck_seller_profile_status_valid",
        ),
        db.Index("ix_seller_profiles_status_created", "approval_status", "created_at"),
    )

    user = db.relationship("User", back_populates="seller_profile", foreign_keys=[user_id])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by_id])


class RiderProfile(TimestampMixin, db.Model):
    __tablename__ = "rider_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    availability_status = db.Column(db.String(20), nullable=False, default="offline")
    __table_args__ = (
        db.CheckConstraint(
            "availability_status IN ('offline', 'available', 'busy', 'suspended')",
            name="ck_rider_profile_status_valid",
        ),
    )

    user = db.relationship("User", back_populates="rider_profile")


class AccountInvitation(TimestampMixin, db.Model):
    __tablename__ = "account_invitations"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    token_digest = db.Column(db.String(64), nullable=False, unique=True)
    invited_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    accepted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    locale = db.Column(db.String(12), nullable=True)
    __table_args__ = (
        db.CheckConstraint("role IN ('rider', 'admin')", name="ck_account_invitation_role_valid"),
        db.Index("ix_account_invitations_pending_email", "email", "accepted_at", "expires_at"),
    )

    inviter = db.relationship("User", foreign_keys=[invited_by_id])


class AppSetting(db.Model):
    __tablename__ = "app_settings"

    id = db.Column(db.Integer, primary_key=True)
    app_name = db.Column(db.String(120), nullable=False, default="NexHaat")
    logo_path = db.Column(db.String(255), nullable=True)
