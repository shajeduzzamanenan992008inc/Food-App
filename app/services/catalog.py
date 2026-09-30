from math import ceil

from sqlalchemy import func, select

from ..extensions import db
from ..models import Category, Product
from ..models.food_reference import FdcCategory, FdcFood
from ..repositories.catalog import (
    active_categories,
    active_products,
    products_for_category,
    search_active_products,
)


def get_active_categories():
    return db.session.scalars(active_categories()).all()


def get_home_products():
    return db.session.scalars(active_products().limit(12)).all()


def _paginate_products(statement, page, per_page):
    total = db.session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    ) or 0
    pages = max(1, ceil(total / per_page))
    page = max(1, min(page, pages))
    products = db.session.scalars(
        statement.limit(per_page).offset((page - 1) * per_page)
    ).all()
    return products, {
        "page": page,
        "pages": pages,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < pages,
    }


def get_menu_products(page=1, per_page=48):
    return _paginate_products(active_products(), page, per_page)


def get_reference_food_categories():
    return db.session.execute(
        select(FdcCategory, func.count(FdcFood.fdc_id).label("food_count"))
        .join(FdcFood, FdcFood.category_id == FdcCategory.id)
        .group_by(FdcCategory.id)
        .order_by(FdcCategory.name)
    ).all()


def get_reference_foods(page=1, per_page=48, category_id=None, query=""):
    statement = select(FdcFood).where(FdcFood.description != "")
    if category_id is not None:
        statement = statement.where(FdcFood.category_id == category_id)
    if query:
        statement = statement.where(FdcFood.description.ilike(f"%{query}%"))

    total = db.session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    ) or 0
    pages = max(1, ceil(total / per_page))
    page = max(1, min(page, pages))
    foods = db.session.scalars(
        statement.order_by(FdcFood.description, FdcFood.fdc_id)
        .limit(per_page)
        .offset((page - 1) * per_page)
    ).all()
    return foods, {
        "page": page,
        "pages": pages,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < pages,
    }


def get_category_by_slug(slug):
    return db.session.scalar(
        select(Category).where(Category.slug == slug, Category.is_active.is_(True))
    )


def get_category_products(category, page=1, per_page=48):
    return _paginate_products(products_for_category(category), page, per_page)


def get_product_by_slug(slug):
    return db.session.scalar(
        active_products().where(Product.slug == slug)
    )


def search_products(query, page=1, per_page=48):
    if not query.strip():
        return [], {"page": 1, "pages": 1, "total": 0, "has_prev": False, "has_next": False}
    return _paginate_products(search_active_products(query), page, per_page)


def search_suggestions(query, limit=8):
    query = (query or "").strip()[:100]
    if len(query) < 2:
        return []
    return db.session.scalars(search_active_products(query).limit(limit)).all()
