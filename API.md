# API and route conventions

The application serves server-rendered HTML routes and a versioned JSON API. State-changing API routes require a CSRF token, and totals, prices, roles, and availability are always recomputed on the server.

## Storefront

- `GET /` — home page with active categories and featured products
- `GET /menu?page=&q=&category_id=&min_price=&max_price=&sort=` — paginated active catalog with marketplace filters and separate optional reference-food search
- `GET /category/<slug>?page=&min_price=&max_price=&sort=` — paginated active category products
- `GET /food/<slug>` — available product detail with localized text and source-language fallback
- `POST /food/<slug>/reviews` — purchase-verified product review (customers only; enters moderation)
- `GET /search?q=&page=&category_id=&min_price=&max_price=&sort=` — bounded, paginated search across name, description, and translations
- `GET /api/search-suggestions?q=` — up to eight bounded catalog suggestions (JSON)
- `GET /health` — database readiness status without exposing connection details
- `GET /health/db` — dedicated database readiness probe for deployment checks
- `POST /language` — persist a supported locale (session or account)

## Notifications

- `GET /notifications` — signed-in inbox with order, delivery, and account updates
- `POST /notifications/<id>/read`, `POST /notifications/read-all` — mark read

## Wishlist

- `GET /wishlist` — signed-in customer's saved products (guests are sent to login)
- `POST /wishlist/add/<product_id>`, `POST /wishlist/remove/<product_id>` — save/remove a product (idempotent; adds a local `next` redirect)

## Versioned JSON API (v1)

A frontend-independent REST API is mounted under `/api/v1`. It reuses the same
services and repositories as the server-rendered pages, and every response uses
one predictable envelope:

```json
{"success": true, "data": {}, "message": "Success"}
{"success": true, "data": [], "message": "Success", "pagination": {"page": 1, "limit": 20, "total": 0}}
{"success": false, "error": {"code": "NOT_FOUND", "message": "Resource not found."}}
```

Money is serialized as a fixed-precision string (for example `"12.50"`) so no
cents are lost, and error responses never include stack traces or internal paths.

- `GET /api/v1/health` — API health probe
- `GET /api/v1/auth/csrf` — CSRF token for session-authenticated API clients (send it back in the `X-CSRFToken` header on `POST`/`PATCH`/`DELETE`)
- `POST /api/v1/auth/register` — start customer or seller signup and email OTP verification (`202`)
- `POST /api/v1/auth/register/verify` — consume the signup OTP and create the account (`201`)
- `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me` — session authentication for Customer/Seller/Rider; Admin password login is refused
- `POST /api/v1/auth/admin/code`, `POST /api/v1/auth/admin/verify` — passwordless Admin OTP sign-in
- `GET /api/v1/products?page=&limit=&q=&category_id=&min_price=&max_price=&sort=` — filtered, paginated active listings
- `GET /api/v1/products/{id}` — product details, localized text, stock and active SKU variants
- `GET /api/v1/categories`, `GET /api/v1/categories/{slug}` — active category list and paginated products
- `GET /api/v1/search?q=&page=&limit=&category_id=&min_price=&max_price=&sort=` — catalog search
- `GET /api/v1/cart`, `POST /api/v1/cart/items`, `PATCH /api/v1/cart/items/{product-or-variant-key}`, `DELETE /api/v1/cart/items/{product-or-variant-key}`, `DELETE /api/v1/cart` — session cart
- `POST /api/v1/checkout/preview`, `POST /api/v1/checkout` — server-priced seller-split COD checkout with transactional stock reservation
- `GET /api/v1/orders`, `GET /api/v1/orders/{number}`, `POST /api/v1/orders/{number}/cancel` — customer history, detail and eligible cancellation
- `GET /api/v1/seller/dashboard`, `GET /api/v1/seller/orders`, `PATCH /api/v1/seller/orders/{id}` — approved-seller metrics and owner-scoped order actions
- `GET /api/v1/seller/products`, `POST /api/v1/seller/products`, `PATCH /api/v1/seller/products/{id}`, `DELETE /api/v1/seller/products/{id}` — owner-scoped product management; create/edit submits for Admin moderation
- `GET /api/v1/admin/dashboard`, `GET /api/v1/admin/users`, `PATCH /api/v1/admin/users/{id}`, `GET /api/v1/admin/sellers`, `PATCH /api/v1/admin/sellers/{id}`
- `GET /api/v1/admin/categories`, `POST /api/v1/admin/categories`, `PATCH|DELETE /api/v1/admin/categories/{id}`
- `GET /api/v1/admin/products`, `PATCH /api/v1/admin/products/{id}`, `GET /api/v1/admin/orders`, `PATCH /api/v1/admin/orders/{id}`, `GET /api/v1/admin/reviews`, `PATCH /api/v1/admin/reviews/{id}`
- `GET /api/v1/products/{id}/reviews` — approved reviews and the rating summary
- `POST /api/v1/products/{id}/reviews` — submit a purchase-verified review (returns `201`; `401` if not a signed-in customer, `422` when the purchase is not eligible)
- `GET /api/v1/notifications` — the signed-in user's notifications and unread count
- `POST /api/v1/notifications/{id}/read` — mark one notification read
- `POST /api/v1/notifications/read-all` — mark every unread notification read
- `GET /api/v1/wishlist` — signed-in customer's saved products with the saved count
- `POST /api/v1/wishlist/items` — save a product (`{"product_id": ...}`; returns `201`; `404` for an unknown product, idempotent when already saved)
- `DELETE /api/v1/wishlist/items/{product_id}` — remove a saved product

API clients authenticate with the existing session cookie. Signup challenges are stored server-side; raw OTP codes and passwords are never stored. Admin OTPs, signup OTPs, and API state-changing requests retain their expiry, throttling, and CSRF protections.

## Cart, checkout, and orders

- `GET /cart`, `POST /cart/add/<product_id>`, `POST /cart/update`, `POST /cart/remove/<product_id>` — session cart
- `GET|POST /checkout` — COD checkout that splits the cart into seller-specific sub-orders
- `GET /orders/<order_number>` — confirmation listing every sub-order in the checkout group
- `GET /my-orders` — signed-in customer order history
- `POST /orders/<order_number>/cancel` — cancel an owned pending/confirmed order and restore reserved inventory

## Authentication and accounts

- `GET|POST /auth/register`, `GET|POST /auth/login`, `POST /auth/logout`
- `GET|POST /auth/forgot-password`, `/auth/verify-reset-code`, `/auth/reset-password` — customer password reset
- `GET|POST /admin/login`, `/auth/verify-admin-login`, `POST /auth/resend-admin-login-code` — passwordless Admin email-OTP sign-in
- `GET|POST /auth/account`, `POST /auth/account/password`, `POST /auth/account/delete` — customer profile, password, and self-deletion
- `GET|POST /auth/admin-account` — Admin profile
- `GET /auth/portal` — legacy workspace entry point (kept for compatibility)
- `POST /auth/admin/invitations`, `/auth/admin/invitations/<id>/resend`, `/revoke`, `GET|POST /auth/invitation/<token>` — staff invitations

## Seller workspace

- `GET /seller/dashboard`, `GET /seller/catalog`, `GET /seller/orders`
- `POST /seller/orders/<id>/status` — confirm/decline pending orders or start preparing confirmed orders
- `GET|POST /seller/account`, `POST /seller/account/password` — store contact details and password
- `GET|POST /seller/products/new`, `GET|POST /seller/products/<id>/edit`
- `GET|POST /seller/products/<id>/variants`, plus variant stock and availability actions

## Rider workspace

- `GET /rider/dashboard` — active and completed deliveries
- `GET|POST /rider/account`, `POST /rider/account/password` — contact details and availability
- `POST /rider/deliveries/<order_id>/status` — validated delivery transition with proof of delivery

## Admin workspace

- `GET /admin` — operations dashboard (seller review, catalog moderation, staff accounts, customers, orders, delivery, audit trail)
- `GET|POST /admin/settings`, `/admin/products/new`, `/admin/products/<id>/edit`, `/admin/categories/new`, `/admin/categories/<id>/edit`, `/admin/customers/new`
- `POST /admin/products/<id>/review`, `/admin/sellers/<profile_id>/review`
- `POST /admin/reviews/<id>/moderate` — approve or reject a product review
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
