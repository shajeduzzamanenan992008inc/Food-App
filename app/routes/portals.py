"""Role-specific workspace blueprints and dashboards."""

from datetime import datetime, timezone
from math import ceil

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request, url_for,
)
from flask_babel import gettext
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import (
    AccountInvitation, AuditEvent, Order, Product, SellerProfile, User, delivery_transition_valid,
)
from ..services.profiles import customer_profile_image_url, ensure_customer_profile
from ..services.audit import record_audit
from ..security import (
    admin_required, customer_required, current_session_user, role_required, save_raster_upload,
)


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
    orders = db.session.scalars(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.rider_id == user.id)
        .order_by(Order.delivery_status.asc(), Order.created_at.desc())
    ).all()
    active = [order for order in orders if order.delivery_status not in {"delivered", "failed"}]
    completed = [order for order in orders if order.delivery_status in {"delivered", "failed"}]
    return render_template(
        "rider/dashboard.html",
        user=user,
        profile=user.rider_profile,
        active=active,
        completed=completed,
    )


@rider_bp.post("/deliveries/<int:order_id>/status")
@role_required("rider")
def update_delivery(order_id):
    user = current_session_user("rider")
    order = db.session.get(Order, order_id)
    if not order or order.rider_id != user.id:
        abort(404)
    target = request.form.get("delivery_status", "")
    if not delivery_transition_valid(order.delivery_status, target):
        flash(gettext("That delivery update is not allowed."), "error")
        return redirect(url_for("rider.dashboard"))
    now = datetime.now(timezone.utc)
    if target == "assigned":
        order.assigned_at = now
        order.picked_up_at = None
        order.out_for_delivery_at = None
    elif target == "picked_up":
        order.picked_up_at = now
    elif target == "out_for_delivery":
        order.out_for_delivery_at = now
    elif target == "delivered":
        note = request.form.get("delivery_note", "").strip()
        if len(note) > 500:
            flash(gettext("The delivery note must be 500 characters or fewer."), "error")
            return redirect(url_for("rider.dashboard"))
        proof = request.files.get("proof")
        if proof and proof.filename:
            filename, upload_error = save_raster_upload(
                proof, current_app.config["PROOF_OF_DELIVERY_FOLDER"], f"pod-{order.id}"
            )
            if upload_error:
                flash(upload_error, "error")
                return redirect(url_for("rider.dashboard"))
            order.delivery_proof = filename
        if not order.delivery_proof and not note:
            flash(gettext("Add a delivery photo or a note as proof of delivery."), "error")
            return redirect(url_for("rider.dashboard"))
        if note:
            order.delivery_note = note
        order.delivered_at = now
        order.status = "delivered"
    elif target == "failed":
        note = request.form.get("delivery_note", "").strip()[:500]
        if note:
            order.delivery_note = note
    order.delivery_status = target
    db.session.commit()
    record_audit("delivery.update", target_type="order", target_id=order.id, detail=target)
    flash(gettext("Delivery status updated."), "success")
    return redirect(url_for("rider.dashboard"))


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
        riders=db.session.scalars(
            select(User)
            .where(User.role == "rider", User.is_active.is_(True))
            .order_by(User.email)
        ).all(),
        audit_events=db.session.scalars(
            select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(50)
        ).all(),
    )
