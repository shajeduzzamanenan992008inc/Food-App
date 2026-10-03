from datetime import datetime, timezone

from sqlalchemy.orm import validates

from ..extensions import db


REVIEW_STATUSES = ("pending", "approved", "rejected")


class Review(db.Model):
    """A purchase-verified product review that must pass Admin moderation."""

    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The reviewer. Nullable so a review survives account deletion.
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The delivered order that proves the purchase.
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rating = db.Column(db.SmallInteger, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    # Snapshot the author name so the review still reads well after account changes.
    author_name = db.Column(db.String(120), nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default="pending", server_default="pending", index=True
    )
    moderation_note = db.Column(db.String(500), nullable=True)
    moderated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    moderated_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    __table_args__ = (
        db.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating_range"),
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')", name="ck_review_status_valid"
        ),
        db.UniqueConstraint(
            "product_id", "user_id", "order_id", name="uq_review_product_user_order"
        ),
        db.Index("ix_reviews_product_status", "product_id", "status"),
    )

    product = db.relationship("Product", back_populates="reviews")
    user = db.relationship("User", foreign_keys=[user_id])
    moderator = db.relationship("User", foreign_keys=[moderated_by_id])

    @validates("rating")
    def validate_rating(self, key, value):
        try:
            rating = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError("Rating must be a whole number from 1 to 5.") from error
        if isinstance(value, bool) or not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5.")
        return rating

    @validates("status")
    def validate_status(self, key, value):
        if value not in REVIEW_STATUSES:
            raise ValueError("Invalid review status.")
        return value
