# Database

The app uses Flask-Migrate/Alembic for schema changes. Apply revisions with `flask db upgrade` before deploying application code. The initial adoption revision creates missing tables on a new database and safely recognizes tables created by earlier app versions. Production startup does not issue schema-changing DDL. Take a database backup before deploying a migration.

The `users` table stores normalized email addresses and Werkzeug password hashes. Customer and admin profiles are linked with foreign keys and one-to-one constraints. `auth_version` invalidates existing sessions after password changes and account activation changes. Password reset digests, expiry times, delivery cooldowns, and a five-attempt limit are stored server-side; raw reset codes are never stored in the database. `auth_throttles` stores keyed hashes of client addresses and applies a shared limit of 10 failed logins per 15-minute window, followed by a five-minute block. Raw addresses are not retained.

Phase 2 adds `categories` and `products`. Category slugs and product slugs are unique and indexed. Product category references use a foreign key with restricted deletion, and active/availability/search fields are indexed. Prices use `Numeric(10, 2)` with database check constraints and Python `Decimal` validation. Customer queries join active categories and available products so unpublished catalog records are not displayed.

Beyond the core `users`, `customers`, `admins`, `addresses`, and `app_settings` tables, the schema now includes:

- `seller_profiles`, `rider_profiles`, and `account_invitations` for role onboarding, approval state, and single-use staff setup links.
- `categories`, `products`, `product_translations`, and `product_variants` for the catalog, seller-authored multilingual text, and SKU stock.
- `orders` and `order_items`. Each order may belong to a `seller` and a `rider`, carries a `checkout_group` and `delivery_fee`, and tracks the delivery workflow through `delivery_status` with per-stage timestamps, proof of delivery, and a note. Order items snapshot product name, price, quantity, and subtotal so later catalog edits do not change historical orders.
- `admin_login_challenges` for passwordless Admin email-OTP challenges (hashed code, expiry, attempts, single use).
- `auth_throttles` for keyed login throttling.
- `outbound_emails` for the durable transactional-email outbox with attempt counts and retry state.
- `audit_events` for the security audit trail (action, actor snapshot, target, detail, and a keyed client-address hash).
- `fdc_*` and `foodon_categories` for the imported reference vocabulary.

Cart state remains in the signed Flask session; no persistent cart table is needed. Confirmed and declined orders remain in the database for customer history and audit; removal is only available through the explicit admin action.

## Food reference data

USDA FoodData Central reference records are stored separately from `products`: reference foods have no invented menu price and cannot be ordered. The `fdc_foods`, `fdc_categories`, `fdc_nutrients`, `fdc_food_nutrients`, and `fdc_food_portions` tables keep source IDs, survey category assignments, nutrient measurements, and portion data. FoodOn product vocabulary is stored in `foodon_categories`, separately from the shop's customer-facing menu categories.

Apply the schema migration with `flask db upgrade`, then import a FoodData Central CSV ZIP with `flask import-fdc --zip-path <archive.zip> --release <release-date> --max-db-mib 400`. Import FoodOn vocabulary with `flask import-foodon --owl-path <foodon.owl> --max-db-mib 400`. Both importers stream records in bounded batches, enforce the database size limit, and roll back the active import if it would exceed that limit. USDA FoodData Central data is public domain under CC0; cite FoodData Central when redistributing the imported records.

The 400 MiB limit is a hard maximum for the configured database. A real dataset cannot provide one million distinct foods for every category; FoodOn supplies a real category vocabulary, while USDA supplies a finite set of food and nutrient records. The importer does not create synthetic rows to fill empty categories.

Monetary values use fixed-precision numeric columns and Python `Decimal`, never floating point. Database constraints validate order totals, payment method, order status, item price, and quantity. Composite indexes support customer order history, admin order lists, and catalog ordering. SQLite connections enforce foreign keys and wait briefly during concurrent writes.
