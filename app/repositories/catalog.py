from sqlalchemy import or_, select
from sqlalchemy.orm import contains_eager

from ..models import Category, Product, ProductTranslation


def active_categories():
    return select(Category).where(Category.is_active.is_(True)).order_by(Category.name.asc())


def active_products():
    return (
        select(Product)
        .join(Product.category)
        .options(contains_eager(Product.category))
        .where(
            Product.is_available.is_(True),
            Product.moderation_status == "approved",
            Category.is_active.is_(True),
        )
        .order_by(Product.is_featured.desc(), Product.name.asc())
    )


def products_for_category(category):
    return active_products().where(Product.category_id == category.id)


def search_active_products(query):
    pattern = f"%{query.strip()}%"
    return active_products().where(
        or_(
            Product.name.ilike(pattern),
            Product.description.ilike(pattern),
            Product.translations.any(
                or_(
                    ProductTranslation.name.ilike(pattern),
                    ProductTranslation.description.ilike(pattern),
                )
            ),
        )
    )
