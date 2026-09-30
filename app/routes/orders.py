from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from ..extensions import db
from ..models import (
    AppSetting, Category, CustomerAddress, CustomerProfile,
    Order, OrderItem, Product, SellerProfile, User,
)
from ..security import admin_required, customer_or_guest_required, current_session_user, save_raster_upload
from ..services.mail import (
    queue_order_confirmation,
    send_order_confirmation,
    send_order_receipt,
    send_order_status,
)


orders_bp = Blueprint("orders", __name__)
DELIVERY_FEE = Decimal("2.50")
STATUSES = ("pending", "confirmed", "preparing", "delivered", "cancelled", "declined")


def parse_quantity(value, default=1):
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(quantity, 20))


def cart_rows():
    raw_cart = session.get("cart", {})
    product_ids = []
    for key in raw_cart:
        try:
            product_ids.append(int(key))
        except (TypeError, ValueError):
            continue
    products = db.session.scalars(
        select(Product).options(joinedload(Product.category)).where(Product.id.in_(product_ids))
    ).all() if product_ids else []
    rows, total = [], Decimal("0.00")
    valid_cart = {}
    for product in products:
        quantity = parse_quantity(raw_cart.get(str(product.id)))
        if not product.is_available or not product.category.is_active:
            continue
        subtotal = product.display_price * quantity
        rows.append({"product": product, "quantity": quantity, "subtotal": subtotal})
        total += subtotal
        valid_cart[str(product.id)] = quantity
    session["cart"] = valid_cart
    return rows, total


@orders_bp.get("/cart")
@customer_or_guest_required
def cart():
    rows, subtotal = cart_rows()
    return render_template("orders/cart.html", rows=rows, subtotal=subtotal, delivery=DELIVERY_FEE, total=subtotal + DELIVERY_FEE if rows else Decimal("0.00"))


@orders_bp.post("/cart/add/<int:product_id>")
@customer_or_guest_required
def add_to_cart(product_id):
    product = db.session.get(Product, product_id)
    if not product or not product.is_available or not product.category.is_active:
        abort(404)
    cart = session.get("cart", {})
    key = str(product_id)
    cart[key] = min(parse_quantity(cart.get(key), default=0) + parse_quantity(request.form.get("quantity")), 20)
    session["cart"] = cart
    flash(f"{product.name} added to your cart.", "success")
    next_url = request.form.get("next", "")
    parsed_next = urlsplit(next_url)
    safe_next = bool(
        next_url.startswith("/")
        and not next_url.startswith("//")
        and not parsed_next.scheme
        and not parsed_next.netloc
        and "\\" not in next_url
    )
    return redirect(next_url if safe_next else url_for("orders.cart"))


@orders_bp.post("/cart/update")
@customer_or_guest_required
def update_cart():
    cart = session.get("cart", {})
    for key, value in request.form.items():
        if key.startswith("quantity_"):
            product_id = key.removeprefix("quantity_")
            try:
                quantity = int(value)
            except (TypeError, ValueError):
                quantity = 0
            if quantity > 0:
                cart[product_id] = min(quantity, 20)
            else:
                cart.pop(product_id, None)
    session["cart"] = cart
    return redirect(url_for("orders.cart"))


@orders_bp.post("/cart/remove/<int:product_id>")
@customer_or_guest_required
def remove_from_cart(product_id):
    cart = session.get("cart", {})
    cart.pop(str(product_id), None)
    session["cart"] = cart
    return redirect(url_for("orders.cart"))


@orders_bp.route("/checkout", methods=["GET", "POST"])
@customer_or_guest_required
def checkout():
    rows, subtotal = cart_rows()
    if not rows:
        flash("Your cart is empty.", "error")
        return redirect(url_for("orders.cart"))
    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        email = request.form.get("email", "").strip() or None
        payment_method = request.form.get("payment_method", "").strip().lower()
        if session.get("user_id"):
            signed_in_user = db.session.get(User, session["user_id"])
            email = signed_in_user.email if signed_in_user else email
        if (
            not email or len(email) > 255 or "@" not in email
            or "." not in email.rsplit("@", 1)[-1]
        ):
            flash("Please provide a valid email address for order updates.", "error")
        elif payment_method != "cod":
            flash("Please choose a supported payment method.", "error")
        elif not 2 <= len(name) <= 120 or not 7 <= len(phone) <= 30 or not 8 <= len(address) <= 2000:
            flash("Please provide a valid name, phone, and delivery address.", "error")
        else:
            order = Order(
                order_number=f"FB-{uuid4().hex.upper()}",
                user_id=session.get("user_id"),
                customer_name=name, phone=phone, email=email, address=address,
                total=subtotal + DELIVERY_FEE, payment_method=payment_method, status="pending",
            )
            for row in rows:
                order.items.append(OrderItem(
                    product_id=row["product"].id, product_name=row["product"].name,
                    price=row["product"].display_price, quantity=row["quantity"], subtotal=row["subtotal"],
                ))
            db.session.add(order)
            db.session.commit()
            session["cart"] = {}
            if current_app.config.get("ASYNC_ORDER_EMAILS", True):
                queue_order_confirmation(order.order_number)
            else:
                send_order_confirmation(order)
            return redirect(url_for("orders.confirmation", order_number=order.order_number))
    customer = None
    user_email = None
    if session.get("user_id"):
        signed_in_user = db.session.get(User, session["user_id"])
        customer = signed_in_user.customer_profile
        user_email = signed_in_user.email
    return render_template(
        "orders/checkout.html", rows=rows, subtotal=subtotal, delivery=DELIVERY_FEE,
        total=subtotal + DELIVERY_FEE, customer=customer, user_email=user_email,
    )


@orders_bp.get("/orders/<order_number>")
def confirmation(order_number):
    order = db.session.scalar(select(Order).where(Order.order_number == order_number))
    if not order or (order.user_id and order.user_id != session.get("user_id")):
        abort(404)
    return render_template("orders/confirmation.html", order=order)


@orders_bp.get("/my-orders")
def my_orders():
    user = current_session_user("customer")
    if not user:
        if session.get("user_id") is not None:
            abort(403)
        return redirect(url_for("auth.login", next=url_for("orders.my_orders")))
    orders = db.session.scalars(
        select(Order).options(selectinload(Order.items))
        .where(Order.user_id == user.id).order_by(Order.created_at.desc())
    ).all()
    return render_template("orders/my_orders.html", orders=orders)


@orders_bp.post("/admin/sellers/<int:profile_id>/review")
@admin_required
def admin_review_seller(profile_id):
    profile = db.session.get(SellerProfile, profile_id)
    if not profile:
        abort(404)
    if profile.approval_status != "pending":
        flash(gettext("This seller application has already been reviewed."), "error")
        return redirect(url_for("admin.dashboard"))
    decision = request.form.get("decision", "")
    if decision not in {"approved", "rejected"}:
        abort(400)
    note = request.form.get("review_note", "").strip()
    if len(note) > 500:
        flash(gettext("The review note must be 500 characters or fewer."), "error")
        return redirect(url_for("admin.dashboard"))
    profile.approval_status = decision
    profile.reviewed_at = datetime.now(timezone.utc)
    profile.reviewed_by_id = session["user_id"]
    profile.review_note = note or None
    db.session.commit()
    flash(
        gettext("Seller application approved.") if decision == "approved"
        else gettext("Seller application rejected."),
        "success",
    )
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/products/<int:product_id>/review")
@admin_required
def admin_review_product(product_id):
    product = db.session.get(Product, product_id)
    if not product or product.seller_id is None or product.moderation_status != "pending":
        abort(404)
    decision = request.form.get("decision", "")
    if decision not in {"approved", "rejected"}:
        abort(400)
    note = request.form.get("review_note", "").strip()
    if len(note) > 500:
        flash(gettext("The review note must be 500 characters or fewer."), "error")
        return redirect(url_for("admin.dashboard"))
    product.moderation_status = decision
    product.is_available = decision == "approved"
    product.moderation_note = note or None
    product.reviewed_at = datetime.now(timezone.utc)
    product.reviewed_by_id = session["user_id"]
    db.session.commit()
    flash(
        gettext("Product listing approved.") if decision == "approved"
        else gettext("Product listing rejected."),
        "success",
    )
    return redirect(url_for("admin.dashboard"))


@orders_bp.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    setting = db.session.get(AppSetting, 1)
    if not setting:
        setting = AppSetting(id=1, app_name="NexHaat")
        db.session.add(setting)
    if request.method == "POST":
        name = request.form.get("app_name", "").strip()
        if len(name) < 2:
            flash("App name must contain at least 2 characters.", "error")
            return render_template("admin/settings.html", setting=setting), 400
        setting.app_name = name[:120]
        logo = request.files.get("logo")
        if logo and logo.filename:
            filename, upload_error = save_raster_upload(
                logo, current_app.config["BRANDING_UPLOAD_FOLDER"], "app-logo"
            )
            if upload_error:
                flash(upload_error, "error")
                return render_template("admin/settings.html", setting=setting), 400
            setting.logo_path = f"uploads/branding/{filename}"
        db.session.commit()
        flash("App branding updated.", "success")
        return redirect(url_for("admin.dashboard"))
    db.session.commit()
    return render_template("admin/settings.html", setting=setting)


@orders_bp.route("/admin/customers/new", methods=["GET", "POST"])
@admin_required
def admin_customer_new():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        min_password_length = current_app.config["MIN_PASSWORD_LENGTH"]
        max_password_length = current_app.config["MAX_PASSWORD_LENGTH"]
        if (
            "@" not in email
            or len(email) > 255
            or not min_password_length <= len(password) <= max_password_length
            or not 2 <= len(name) <= 120
            or not 7 <= len(phone) <= 30
        ):
            flash(
                f"Enter valid customer details and a password ({min_password_length}–{max_password_length} characters).",
                "error",
            )
        elif db.session.scalar(select(User).where(User.email == email)):
            flash("That email is already registered.", "error")
        else:
            user = User(email=email, role="customer")
            user.set_password(password)
            user.customer_profile = CustomerProfile(full_name=name, phone=phone)
            db.session.add(user)
            db.session.commit()
            flash("Customer added.", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/customer_form.html")


@orders_bp.post("/admin/customers/<int:user_id>/remove")
@admin_required
def admin_customer_remove(user_id):
    user = db.session.get(User, user_id)
    if not user or user.role != "customer":
        abort(404)
    db.session.delete(user)
    db.session.commit()
    flash("Customer removed.", "success")
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/customers/<int:user_id>/toggle-active")
@admin_required
def admin_customer_toggle_active(user_id):
    user = db.session.get(User, user_id)
    if not user or user.role != "customer":
        abort(404)
    user.is_active = not user.is_active
    user.auth_version += 1
    db.session.commit()
    flash(f"Customer account {'activated' if user.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin.dashboard"))


@orders_bp.get("/admin/orders/<int:order_id>")
@admin_required
def admin_order_detail(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)
    return render_template("admin/order_detail.html", order=order)


def _set_admin_order_status(order_id, status):
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)
    order.status = status
    db.session.commit()
    send_order_status(order)
    if status == "confirmed":
        send_order_receipt(order)
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/orders/<int:order_id>/confirm")
@admin_required
def admin_order_confirm(order_id):
    return _set_admin_order_status(order_id, "confirmed")


@orders_bp.post("/admin/orders/<int:order_id>/decline")
@admin_required
def admin_order_decline(order_id):
    return _set_admin_order_status(order_id, "declined")


@orders_bp.post("/admin/orders/<int:order_id>/remove")
@admin_required
def admin_order_remove(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)
    db.session.delete(order)
    db.session.commit()
    flash("Order removed permanently.", "success")
    return redirect(url_for("admin.dashboard"))


def _set_all_pending_order_status(status):
    pending_orders = db.session.scalars(
        select(Order).where(Order.status == "pending").order_by(Order.created_at)
    ).all()
    for order in pending_orders:
        order.status = status
    db.session.commit()
    for order in pending_orders:
        send_order_status(order)
        if status == "confirmed":
            send_order_receipt(order)
    flash(f"{len(pending_orders)} pending order(s) marked {status}.", "success")
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/orders/confirm-all")
@admin_required
def admin_order_confirm_all():
    return _set_all_pending_order_status("confirmed")


@orders_bp.post("/admin/orders/decline-all")
@admin_required
def admin_order_decline_all():
    return _set_all_pending_order_status("declined")


@orders_bp.route("/admin/products/new", methods=["GET", "POST"])
@admin_required
def admin_product_new():
    categories = db.session.scalars(select(Category).order_by(Category.name)).all()
    if request.method == "POST":
        try:
            price = Decimal(request.form["price"])
            discount_price = Decimal(request.form["discount_price"]) if request.form.get("discount_price") else None
            category_id = int(request.form["category_id"])
            name = request.form["name"].strip()
            slug = request.form["slug"].strip()
            description = request.form["description"].strip()
            if (
                not db.session.get(Category, category_id)
                or not 2 <= len(name) <= 160
                or len(description) > 10000
            ):
                raise ValueError("Invalid product fields")
            product = Product(
                category_id=category_id, name=name, slug=slug, description=description,
                price=price, discount_price=discount_price, is_available="is_available" in request.form,
            )
            if len(product.slug) > 180 or db.session.scalar(
                select(Product.id).where(Product.slug == product.slug)
            ):
                raise ValueError("Duplicate or invalid product slug")
        except (KeyError, TypeError, ValueError, ArithmeticError):
            flash("Please enter valid product details.", "error")
            return render_template("admin/product_form.html", product=None, categories=categories), 400
        db.session.add(product)
        db.session.commit()
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/product_form.html", product=None, categories=categories)


@orders_bp.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_product_edit(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)
    categories = db.session.scalars(select(Category).order_by(Category.name)).all()
    if request.method == "POST":
        try:
            category_id = int(request.form["category_id"])
            name = request.form["name"].strip()
            description = request.form["description"].strip()
            if (
                not db.session.get(Category, category_id)
                or not 2 <= len(name) <= 160
                or len(description) > 10000
            ):
                raise ValueError("Invalid product fields")
            candidate = Product(
                category_id=category_id,
                name=name,
                slug=request.form["slug"].strip(),
                description=description,
                price=Decimal(request.form["price"]),
                discount_price=Decimal(request.form["discount_price"]) if request.form.get("discount_price") else None,
                is_available="is_available" in request.form,
            )
            if len(candidate.slug) > 180 or db.session.scalar(
                select(Product.id).where(Product.slug == candidate.slug, Product.id != product.id)
            ):
                raise ValueError("Duplicate or invalid product slug")
        except (KeyError, TypeError, ValueError, ArithmeticError):
            flash("Please enter valid product details.", "error")
            return render_template("admin/product_form.html", product=product, categories=categories), 400
        product.name = candidate.name
        product.slug = candidate.slug
        product.category_id = candidate.category_id
        product.description = candidate.description
        product.price = candidate.price
        product.discount_price = candidate.discount_price
        product.is_available = "is_available" in request.form
        db.session.commit()
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/product_form.html", product=product, categories=categories)


@orders_bp.post("/admin/products/<int:product_id>/delete")
@admin_required
def admin_product_delete(product_id):
    product = db.session.get(Product, product_id)
    if product:
        product.is_available = False
        db.session.commit()
    return redirect(url_for("admin.dashboard"))


@orders_bp.route("/admin/categories/new", methods=["GET", "POST"])
@admin_required
def admin_category_new():
    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            description = request.form.get("description", "").strip()
            if not 2 <= len(name) <= 100 or len(description) > 5000:
                raise ValueError("Invalid category fields")
            category = Category(name=name, slug=request.form["slug"].strip(), description=description)
            if len(category.slug) > 120 or db.session.scalar(
                select(Category.id).where(Category.slug == category.slug)
            ):
                raise ValueError("Duplicate or invalid category slug")
        except (KeyError, TypeError, ValueError):
            flash("Please enter valid category details.", "error")
            return render_template("admin/category_form.html", category=None), 400
        db.session.add(category)
        db.session.commit()
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/category_form.html", category=None)


@orders_bp.route("/admin/categories/<int:category_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_category_edit(category_id):
    category = db.session.get(Category, category_id)
    if not category:
        abort(404)
    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            description = request.form.get("description", "").strip()
            if not 2 <= len(name) <= 100 or len(description) > 5000:
                raise ValueError("Invalid category fields")
            candidate = Category(name=name, slug=request.form["slug"].strip(), description=description)
            if len(candidate.slug) > 120 or db.session.scalar(
                select(Category.id).where(Category.slug == candidate.slug, Category.id != category.id)
            ):
                raise ValueError("Duplicate or invalid category slug")
        except (KeyError, TypeError, ValueError):
            flash("Please enter valid category details.", "error")
            return render_template("admin/category_form.html", category=category), 400
        category.name = candidate.name
        category.slug = candidate.slug
        category.description = candidate.description
        db.session.commit()
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/category_form.html", category=category)


@orders_bp.post("/admin/categories/<int:category_id>/delete")
@admin_required
def admin_category_delete(category_id):
    category = db.session.get(Category, category_id)
    if category:
        category.is_active = False
        for product in category.products:
            product.is_available = False
        db.session.commit()
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/orders/<int:order_id>/status")
@admin_required
def admin_order_status(order_id):
    order = db.session.get(Order, order_id)
    status = request.form.get("status")
    if not order or status not in STATUSES:
        abort(404)
    order.status = status
    db.session.commit()
    send_order_status(order)
    if status == "confirmed":
        send_order_receipt(order)
    return redirect(url_for("admin.dashboard"))
