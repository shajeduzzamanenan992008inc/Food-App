"""Role-specific workspace blueprints and dashboards."""

from math import ceil

from flask import Blueprint, abort, render_template, request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import AccountInvitation, Order, Product, SellerProfile, User
from ..services.profiles import customer_profile_image_url, ensure_customer_profile
from ..security import admin_required, customer_required, current_session_user, role_required


customer_bp = Blueprint("customer", __name__, url_prefix="/customer")
rider_bp = Blueprint("rider", __name__, url_prefix="/rider")
admin_bp = Blueprint("admin", __name__)


@customer_bp.get("/dashboard")
@customer_required
def dashboard():
    user = current_session_user("customer")
    profile = ensure_customer_profile(user)
    return render_template(
        "customer/dashboard.html", user=user, profile=profile,
        profile_image_url=customer_profile_image_url(profile),
    )


@rider_bp.get("/dashboard")
@role_required("rider")
def dashboard():
    user = current_session_user("rider")
    if not user.rider_profile:
        abort(403)
    return render_template("rider/dashboard.html", user=user, profile=user.rider_profile)


@admin_bp.get("/admin")
@admin_required
def dashboard():
    page_size = 50
    order_count = db.session.scalar(select(func.count(Order.id))) or 0
    customer_count = db.session.scalar(
        select(func.count(User.id)).where(User.role == "customer")
    ) or 0
    pending_count = db.session.scalar(
        select(func.count(Order.id)).where(Order.status == "pending")
    ) or 0
    order_pages = max(1, ceil(order_count / page_size))
    customer_pages = max(1, ceil(customer_count / page_size))
    order_page = min(max(1, request.args.get("orders_page", 1, type=int)), order_pages)
    customer_page = min(max(1, request.args.get("customers_page", 1, type=int)), customer_pages)

    return render_template(
        "admin/dashboard.html",
        orders=db.session.scalars(
            select(Order).order_by(Order.created_at.desc()).limit(page_size)
            .offset((order_page - 1) * page_size)
        ).all(),
        customers=db.session.scalars(
            select(User).options(selectinload(User.customer_profile))
            .where(User.role == "customer").order_by(User.email).limit(page_size)
            .offset((customer_page - 1) * page_size)
        ).all(),
        order_count=order_count,
        customer_count=customer_count,
        pending_count=pending_count,
        order_page=order_page,
        order_pages=order_pages,
        customer_page=customer_page,
        customer_pages=customer_pages,
        pending_sellers=db.session.scalars(
            select(SellerProfile)
            .where(SellerProfile.approval_status == "pending")
            .order_by(SellerProfile.created_at.asc())
            .limit(100)
        ).all(),
        pending_seller_count=db.session.scalar(
            select(func.count(SellerProfile.id)).where(SellerProfile.approval_status == "pending")
        ) or 0,
        pending_products=db.session.scalars(
            select(Product)
            .options(selectinload(Product.seller).selectinload(User.seller_profile), selectinload(Product.category))
            .where(Product.seller_id.is_not(None), Product.moderation_status == "pending")
            .order_by(Product.created_at.asc())
            .limit(100)
        ).all(),
        pending_product_count=db.session.scalar(
            select(func.count(Product.id)).where(
                Product.seller_id.is_not(None), Product.moderation_status == "pending"
            )
        ) or 0,
        invitations=db.session.scalars(
            select(AccountInvitation)
            .where(AccountInvitation.accepted_at.is_(None))
            .order_by(AccountInvitation.created_at.desc())
            .limit(50)
        ).all(),
        statuses=("pending", "confirmed", "preparing", "delivered", "cancelled", "declined"),
    )
