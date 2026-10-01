# API and route conventions

The application serves server-rendered HTML routes plus one JSON suggestion endpoint. State-changing routes require a CSRF token, and totals, prices, roles, and availability are always recomputed on the server.

## Storefront
- `GET /` — home page with active categories and featured products
- `GET /menu?page=&q=&category_id=` — paginated active catalog with optional reference-food search
- `GET /category/<slug>?page=` — paginated active category products
- `GET /food/<slug>` — available product detail with localized text and source-language fallback
- `GET /search?q=&page=` — bounded, paginated case-insensitive search across name, description, and translations
- `GET /api/search-suggestions?q=` — up to eight bounded catalog suggestions (JSON)
- `GET /health` — database readiness status without exposing connection details
- `POST /language` — persist a supported locale (session or account)

## Cart, checkout, and orders
- `GET /cart`, `POST /cart/add/<product_id>`, `POST /cart/update`, `POST /cart/remove/<product_id>` — session cart
- `GET|POST /checkout` — COD checkout that splits the cart into seller-specific sub-orders
- `GET /orders/<order_number>` — confirmation listing every sub-order in the checkout group
- `GET /my-orders` — signed-in customer order history

## Authentication and accounts
- `GET|POST /auth/register`, `GET|POST /auth/login`, `POST /auth/logout`
- `GET|POST /auth/forgot-password`, `/auth/verify-reset-code`, `/auth/reset-password` — customer password reset
- `GET|POST /admin/login`, `/auth/verify-admin-login`, `POST /auth/resend-admin-login-code` — passwordless Admin email-OTP sign-in
- `GET|POST /auth/account`, `POST /auth/account/password`, `POST /auth/account/delete` — customer profile, password, and self-deletion
- `GET|POST /auth/admin-account` — Admin profile
- `GET /auth/portal` — legacy workspace entry point (kept for compatibility)
- `POST /auth/admin/invitations`, `/auth/admin/invitations/<id>/resend`, `/revoke`, `GET|POST /auth/invitation/<token>` — staff invitations

## Seller workspace
- `GET /seller/dashboard`, `GET /seller/catalog`
- `GET|POST /seller/products/new`, `GET|POST /seller/products/<id>/edit`
- `GET|POST /seller/products/<id>/variants`, plus variant stock and availability actions

## Rider workspace
- `GET /rider/dashboard` — active and completed deliveries
- `POST /rider/deliveries/<order_id>/status` — validated delivery transition with proof of delivery

## Admin workspace
- `GET /admin` — operations dashboard (seller review, catalog moderation, staff accounts, customers, orders, delivery, audit trail)
- `GET|POST /admin/settings`, `/admin/products/new`, `/admin/products/<id>/edit`, `/admin/categories/new`, `/admin/categories/<id>/edit`, `/admin/customers/new`
- `POST /admin/products/<id>/review`, `/admin/sellers/<profile_id>/review`
- `POST /admin/orders/<id>/status`, `/admin/orders/<id>/assign`, `/admin/orders/<id>/confirm`, `/admin/orders/<id>/decline`, `/admin/orders/confirm-all`, `/admin/orders/decline-all`
- `POST /admin/accounts/<id>/remove` — delete a Seller, Rider, or sub-Admin (primary Admin only)
- `POST /admin/customers/<id>/toggle-active`

## CLI
- `flask --app run.py db upgrade` — apply migrations
- `flask --app run.py ensure-admin`, `flask --app run.py create-admin` — Admin bootstrap
- `flask --app run.py seed-catalog` — curated category seed
- `flask --app run.py import-fdc` / `import-foodon` — reference-data import with the database ceiling
- `flask --app run.py retry-emails` — resend queued transactional email
- `flask --app run.py db-size`, `flask --app run.py backup-db --to <file>`, `flask --app run.py restore-db --from <file>`
- `flask --app run.py production-check` — production launch readiness review

Future JSON endpoints should return consistent success/error envelopes and validate input at the boundary.

