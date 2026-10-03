from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from ..extensions import db
from ..models import (
    AppSetting, Category, CustomerAddress, CustomerProfile,
    Order, Product, Review, SellerProfile, User,
)
from ..security import (
    admin_required, customer_or_guest_required, current_session_user,
    is_primary_admin, primary_admin_required, save_raster_upload,
)
from ..services.audit import record_audit
from ..services.mail import (
    enqueue_order_emails,
    queue_order_receipt,
    queue_order_status,
)
from ..services.notifications import notify
from ..services.orders import release_reserved_stock, transition_order
from ..services.checkout import CheckoutError, DELIVERY_FEE, create_checkout_orders


orders_bp = Blueprint("orders", __name__)
STATUSES = ("pending", "confirmed", "preparing", "delivered", "cancelled", "declined")


def parse_quantity(value, default=1):
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(quantity, 20))


def _cart_key(product_id, variant_id=None):
    return f"{product_id}:{variant_id}" if variant_id else str(product_id)


def _parse_cart_key(value):
    try:
        product_part, separator, variant_part = str(value).partition(":")
        product_id = int(product_part)
        variant_id = int(variant_part) if separator else None
    except (TypeError, ValueError):
        return None, None
    return product_id, variant_id


def cart_rows():
    raw_cart = session.get("cart", {})
    parsed_rows = [(_parse_cart_key(key), key, quantity) for key, quantity in raw_cart.items()]
    product_ids = {parsed[0] for parsed, _key, _quantity in parsed_rows if parsed[0] is not None}
    products = db.session.scalars(
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.variants))
        .where(Product.id.in_(product_ids))
    ).all() if product_ids else []
    product_by_id = {product.id: product for product in products}
    rows, total = [], Decimal("0.00")
    valid_cart = {}
    for (product_id, variant_id), _old_key, raw_quantity in parsed_rows:
        product = product_by_id.get(product_id)
        if product is None:
            continue
        if not product.is_available or not product.category.is_active:
            continue
        active_variants = [variant for variant in product.variants if variant.is_active]
        variant = next(
            (item for item in active_variants if item.id == variant_id), None
        ) if variant_id else None
        if variant_id and variant is None:
            continue
        if not variant and active_variants:
            if len(active_variants) != 1:
                continue
            variant = active_variants[0]
        available_stock = variant.stock_quantity if variant else product.stock_quantity
        if available_stock <= 0:
            continue
        quantity = parse_quantity(raw_quantity)
        price = variant.price if variant and variant.price is not None else product.display_price
        subtotal = price * quantity
        key = _cart_key(product.id, variant.id if variant else None)
        rows.append({
            "product": product,
            "variant": variant,
            "variant_id": variant.id if variant else None,
            "variant_label": f"{variant.option_name}: {variant.option_value}" if variant else None,
            "cart_key": key,
            "price": price,
            "available_stock": available_stock,
            "quantity": quantity,
            "subtotal": subtotal,
            "seller_id": product.seller_id,
        })
        total += subtotal
        valid_cart[key] = quantity
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
    active_variants = [variant for variant in product.variants if variant.is_active]
    variant_id = request.form.get("variant_id", type=int)
    variant = next((item for item in active_variants if item.id == variant_id), None)
    if active_variants and variant is None:
        flash(gettext("Choose a product option before adding it to your cart."), "error")
        return redirect(url_for("main.food", slug=product.slug))
    stock = variant.stock_quantity if variant else product.stock_quantity
    if stock <= 0:
        flash(gettext("This item is out of stock."), "error")
        return redirect(url_for("main.food", slug=product.slug))
    cart = session.get("cart", {})
    key = _cart_key(product_id, variant.id if variant else None)
    cart[key] = min(
        parse_quantity(cart.get(key), default=0) + parse_quantity(request.form.get("quantity")),
        stock,
        20,
    )
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
            cart_key = key.removeprefix("quantity_")
            try:
                quantity = int(value)
            except (TypeError, ValueError):
                quantity = 0
            if quantity > 0:
                cart[cart_key] = min(quantity, 20)
            else:
                cart.pop(cart_key, None)
    session["cart"] = cart
    cart_rows()
    return redirect(url_for("orders.cart"))


@orders_bp.post("/cart/remove/<int:product_id>")
@customer_or_guest_required
def remove_from_cart(product_id):
    cart = session.get("cart", {})
    variant_id = request.form.get("variant_id", type=int)
    cart.pop(_cart_key(product_id, variant_id), None)
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
        user = current_session_user("customer")
        email = user.email if user else request.form.get("email", "").strip() or None
        payment_method = request.form.get("payment_method", "").strip().lower()
        try:
            orders = create_checkout_orders(
                user,
                rows,
                name=name,
                phone=phone,
                address=address,
                email=email,
                payment_method=payment_method,
            )
        except CheckoutError as error:
            db.session.rollback()
            flash(gettext(str(error)), "error")
        else:
            session["cart"] = {}
            return redirect(url_for("orders.confirmation", order_number=orders[0].order_number))
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
    sub_orders = [order]
    if order.checkout_group:
        sub_orders = db.session.scalars(
            select(Order).options(selectinload(Order.items))
            .where(Order.checkout_group == order.checkout_group)
            .order_by(Order.order_number)
        ).all()
    grand_total = sum((item.total for item in sub_orders), Decimal("0.00"))
    return render_template(
        "orders/confirmation.html",
        order=order, sub_orders=sub_orders, grand_total=grand_total,
    )


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


@orders_bp.post("/orders/<order_number>/cancel")
def customer_order_cancel(order_number):
    user = current_session_user("customer")
    if not user:
        if session.get("user_id") is not None:
            abort(403)
        return redirect(url_for("auth.login", next=url_for("orders.my_orders")))
    order = db.session.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.order_number == order_number, Order.user_id == user.id)
        .with_for_update()
    )
    if not order:
        abort(404)
    if order.status not in {"pending", "confirmed"} or not transition_order(order, "cancelled"):
        flash(gettext("This order can no longer be cancelled."), "error")
        return redirect(url_for("orders.my_orders"))
    db.session.commit()
    record_audit("order.cancel", actor=user, target_type="order", target_id=order.id)
    queue_order_status(order)
    if order.seller_id:
        notify(
            order.seller_id,
            gettext("Order %(number)s was cancelled by the customer.", number=order.order_number),
            type="order",
            link=url_for("seller.orders"),
        )
    flash(gettext("Your order was cancelled."), "success")
    return redirect(url_for("orders.my_orders"))


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
    record_audit("seller.review", target_type="seller_profile", target_id=profile_id, detail=decision)
    if decision == "approved":
        notify(
            profile.user_id,
            gettext("Your store was approved. You can now publish products."),
            type="account",
            link=url_for("seller.dashboard"),
        )
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
    record_audit("catalog.product_review", target_type="product", target_id=product_id, detail=decision)
    flash(
        gettext("Product listing approved.") if decision == "approved"
        else gettext("Product listing rejected."),
        "success",
    )
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/reviews/<int:review_id>/moderate")
@admin_required
def admin_moderate_review(review_id):
    review = db.session.get(Review, review_id)
    if not review or review.status != "pending":
        abort(404)
    decision = request.form.get("decision", "")
    if decision not in {"approved", "rejected"}:
        abort(400)
    note = request.form.get("review_note", "").strip()
    if len(note) > 500:
        flash(gettext("The review note must be 500 characters or fewer."), "error")
        return redirect(url_for("admin.dashboard"))
    review.status = decision
    review.moderation_note = note or None
    review.moderated_at = datetime.now(timezone.utc)
    review.moderated_by_id = session["user_id"]
    db.session.commit()
    record_audit("review.moderate", target_type="review", target_id=review_id, detail=decision)
    flash(
        gettext("Review approved.") if decision == "approved" else gettext("Review rejected."),
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
        record_audit("settings.update", target_type="app_setting", detail=setting.app_name)
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
    email = user.email
    db.session.delete(user)
    db.session.commit()
    record_audit("customer.remove", target_type="user", target_id=user_id, detail=f"customer:{email}")
    flash(gettext("Customer removed."), "success")
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/customers/<int:user_id>/toggle-active")
@admin_required
def admin_customer_toggle_active(user_id):
    user = db.session.get(User, user_id)
    if not user or user.role != "customer":
        abort(404)
    action = request.form.get("action")
    if action == "activate":
        user.is_active = True
    elif action == "deactivate":
        user.is_active = False
    else:
        user.is_active = not user.is_active
    user.auth_version += 1
    db.session.commit()
    status_key = "activated" if user.is_active else "deactivated"
    record_audit(f"customer.{status_key}", target_type="user", target_id=user.id, detail=f"customer:{user.email}")
    if user.is_active:
        flash(gettext("Customer account activated."), "success")
    else:
        flash(gettext("Customer account deactivated."), "success")
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/customers/<int:user_id>/activate")
@admin_required
def admin_customer_activate(user_id):
    user = db.session.get(User, user_id)
    if not user or user.role != "customer":
        abort(404)
    user.is_active = True
    user.auth_version += 1
    db.session.commit()
    record_audit("customer.activated", target_type="user", target_id=user.id, detail=f"customer:{user.email}")
    flash(gettext("Customer account activated."), "success")
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/customers/<int:user_id>/deactivate")
@admin_required
def admin_customer_deactivate(user_id):
    user = db.session.get(User, user_id)
    if not user or user.role != "customer":
        abort(404)
    user.is_active = False
    user.auth_version += 1
    db.session.commit()
    record_audit("customer.deactivated", target_type="user", target_id=user.id, detail=f"customer:{user.email}")
    flash(gettext("Customer account deactivated."), "success")
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/accounts/<int:user_id>/remove")
@primary_admin_required
def admin_account_remove(user_id):
    """Delete a Seller, Rider, or sub-Admin. The primary Admin is protected."""
    user = db.session.get(User, user_id)
    if not user or user.role not in {"seller", "rider", "admin"}:
        abort(404)
    if is_primary_admin(user):
        flash(gettext("The primary Admin account cannot be deleted."), "error")
        return redirect(url_for("admin.dashboard"))
    if user.id == session.get("user_id"):
        flash(gettext("You cannot delete your own account here."), "error")
        return redirect(url_for("admin.dashboard"))
    detail = f"{user.role}:{user.email}"
    db.session.delete(user)
    db.session.commit()
    record_audit("account.remove", target_type="user", target_id=user_id, detail=detail)
    flash(gettext("Account removed."), "success")
    return redirect(url_for("admin.dashboard"))


@orders_bp.get("/admin/orders/<int:order_id>")
@admin_required
def admin_order_detail(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)
    return render_template("admin/order_detail.html", order=order)


def _set_admin_order_status(order_id, status):
    order = db.session.scalar(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    if not order:
        abort(404)
    if not transition_order(order, status):
        flash(gettext("That order status transition is not allowed."), "error")
        return redirect(url_for("admin.dashboard"))
    db.session.commit()
    record_audit("order.status", target_type="order", target_id=order.id, detail=status)
    queue_order_status(order)
    if status == "confirmed":
        queue_order_receipt(order)
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
    order = db.session.scalar(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    if not order:
        abort(404)
    if order.status in {"pending", "confirmed", "preparing"}:
        release_reserved_stock(order)
    db.session.delete(order)
    db.session.commit()
    flash("Order removed permanently.", "success")
    return redirect(url_for("admin.dashboard"))


def _set_all_pending_order_status(status):
    pending_orders = db.session.scalars(
        select(Order).options(selectinload(Order.items))
        .where(Order.status == "pending").order_by(Order.created_at)
    ).all()
    for order in pending_orders:
        transition_order(order, status)
    db.session.commit()
    for order in pending_orders:
        queue_order_status(order)
        if status == "confirmed":
            queue_order_receipt(order)
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
    order = db.session.scalar(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    status = request.form.get("status")
    if not order or status not in STATUSES:
        abort(404)
    if not transition_order(order, status):
        flash(gettext("That order status transition is not allowed."), "error")
        return redirect(url_for("admin.dashboard"))
    db.session.commit()
    queue_order_status(order)
    if status == "confirmed":
        queue_order_receipt(order)
    if order.user_id:
        notify(
            order.user_id,
            gettext(
                "Order %(number)s is now %(status)s.",
                number=order.order_number,
                status=status,
            ),
            type="order",
            link=url_for("orders.confirmation", order_number=order.order_number),
        )
    return redirect(url_for("admin.dashboard"))


@orders_bp.post("/admin/orders/<int:order_id>/assign")
@admin_required
def admin_assign_rider(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)
    rider_id = request.form.get("rider_id", type=int)
    if rider_id:
        rider = db.session.get(User, rider_id)
        if not rider or rider.role != "rider" or rider.rider_profile is None:
            flash(gettext("Choose an active delivery rider."), "error")
            return redirect(url_for("admin.dashboard"))
        order.rider_id = rider.id
        order.delivery_status = "assigned"
        order.assigned_at = datetime.now(timezone.utc)
        order.delivery_note = None
        flash(gettext("Rider assigned to this delivery."), "success")
    else:
        order.rider_id = None
        order.delivery_status = "unassigned"
        order.assigned_at = None
        order.picked_up_at = None
        order.out_for_delivery_at = None
        order.delivered_at = None
        flash(gettext("Delivery unassigned."), "success")
    db.session.commit()
    record_audit(
        "delivery.assign",
        target_type="order",
        target_id=order.id,
        detail=f"rider={order.rider_id}" if order.rider_id else "cleared",
    )
    if order.rider_id:
        notify(
            order.rider_id,
            gettext("A new delivery was assigned to you: %(number)s.", number=order.order_number),
            type="delivery",
            link=url_for("rider.dashboard"),
        )
    return redirect(url_for("admin.dashboard"))
