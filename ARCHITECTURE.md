# Architecture

The project uses an application factory in `app/__init__.py`. Extensions are initialized without an app in `app/extensions.py`, allowing the same models and services to be used by tests, CLI commands, and production entry points.

HTTP routes live in blueprints under `app/routes`. Catalog routes delegate active filtering and lookups to `app/services/catalog.py`, which uses `app/repositories/catalog.py` query builders. This keeps route handlers focused on HTTP concerns and ensures unavailable products are not exposed through normal customer catalog routes.

Catalog prices use SQL `Numeric(10, 2)` and Python `Decimal`; floating-point money calculations are not used. Product and category slugs are normalized and unique. Catalog pages are limited to 48 records, while the admin order and customer tables are paginated. Uploaded images are restricted to JPEG, PNG, and WebP, checked against their file signatures, and limited to 2 MB; active SVG uploads are rejected.

Users are represented by one `users` table with a role and separate one-to-one profile tables (`customers` and `admins`). Password reset state and attempt counts live in the database, while `auth_version` revokes sessions after password changes. Login throttling uses a keyed client-address hash in the database so it works across workers without storing raw addresses.

Flask-Migrate owns production schema changes. Production app startup does not create or alter tables; deployments apply migrations before starting workers. The adoption revision preserves databases created by earlier app versions. SQLite connections enable foreign-key enforcement and a write wait timeout for reliable local development.

USDA FoodData Central reference foods and nutrient observations live in separate `fdc_*` tables, not in the orderable menu product table. FoodOn taxonomy terms live in `foodon_categories`; they are vocabulary records and are not automatically assigned to a product when no authoritative mapping is present. The explicit `flask import-fdc` and `flask import-foodon` commands stream public source files into the configured SQLite or PostgreSQL database and enforce a maximum database size of 400 MiB by default.

Responses set a restrictive Content Security Policy, MIME sniffing and framing protections, referrer and permissions policies, and HSTS on secure production requests. CSRF protection covers state-changing forms.

## Extension rules

- Keep secrets in environment variables.
- Use migrations for schema changes after the initial prototype.
- Keep order creation transactional and server-side price validated.
- Add authorization decorators before exposing admin routes.
