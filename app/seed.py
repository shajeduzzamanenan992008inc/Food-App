"""Seed only the curated marketplace taxonomy, never fabricated products."""
from sqlalchemy import select

from .extensions import db
from .models import Category


STARTER_CATEGORIES = (
    ("Fruits & Vegetables", "fruits-vegetables"),
    ("Meat & Seafood", "meat-seafood"),
    ("Dairy & Eggs", "dairy-eggs"),
    ("Bread & Bakery", "bread-bakery"),
    ("Rice, Grains & Pasta", "rice-grains-pasta"),
    ("Beans, Peas & Lentils", "beans-peas-lentils"),
    ("Spices & Seasonings", "spices-seasonings"),
    ("Cooking Oils & Sauces", "cooking-oils-sauces"),
    ("Beverages", "beverages"),
    ("Snacks & Sweets", "snacks-sweets"),
    ("Prepared Foods", "prepared-foods"),
    ("Frozen Foods", "frozen-foods"),
    ("Pantry Essentials", "pantry-essentials"),
    ("Household Essentials", "household-essentials"),
    ("Personal Care", "personal-care"),
    ("Home & Kitchen", "home-kitchen"),
    ("Fashion & Accessories", "fashion-accessories"),
    ("Electronics", "electronics"),
    ("Men's Clothing", "mens-clothing"),
    ("Women's Clothing", "womens-clothing"),
    ("Kids' Clothing", "kids-clothing"),
    ("Shoes & Footwear", "shoes-footwear"),
    ("Bags & Luggage", "bags-luggage"),
    ("Mobile Phones & Tablets", "mobile-phones-tablets"),
    ("Computers & Accessories", "computers-accessories"),
    ("TV, Audio & Video", "tv-audio-video"),
    ("Home Appliances", "home-appliances"),
    ("Smart Home & Wearables", "smart-home-wearables"),
    ("Beauty & Personal Care", "beauty-personal-care"),
    ("Toys & Baby Products", "toys-baby-products"),
    ("Sports & Outdoors", "sports-outdoors"),
    ("Automotive Accessories", "automotive-accessories"),
    ("Furniture & Home Decor", "furniture-home-decor"),
    ("Tools & Hardware", "tools-hardware"),
    ("Books & Stationery", "books-stationery"),
)


def seed_catalog_data():
    """Create useful categories without inventing food listings or prices."""
    existing_slugs = set(db.session.scalars(
        select(Category.slug).where(Category.slug.in_([slug for _, slug in STARTER_CATEGORIES]))
    ).all())
    created = 0
    for name, slug in STARTER_CATEGORIES:
        if slug in existing_slugs:
            continue
        db.session.add(Category(
            name=name,
            slug=slug,
            description="Curated NexHaat marketplace category.",
        ))
        created += 1
    db.session.commit()
    return created


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        print(f"Catalog seed completed: {seed_catalog_data()} categories created.")
