# Changelog

## Unreleased

- Fixed the header **Account** button for sellers and riders: it used to send every non-Admin role to the customer-only `/auth/account` and fail with `403`. Sellers now get `/seller/account` and riders `/rider/account`, with profile and password forms.
- Fixed the seller product form (`/seller/products/new`): the page address (slug) is now optional and derived from the product name, the exact validation reason is shown instead of a generic message (for example "Discount price must be lower than the regular price."), field-level validation and error messages were added, and the submit button is disabled with an explanation when no active category exists.
- Redesigned all transactional emails onto a shared, table-based, Outlook-safe layout that follows the project design reference (brand blue `#087cff`/`#065cc0`, `#e7ebf0` page, 24px radii), with a preheader, brand header, and footer. One-time codes now render in a selectable monospace block so the code can be copied. A standalone copy-paste reference lives at `docs/email-design/reference.html`.
- Added the customer wishlist: the `wishlist_items` table (revision `20261006_13`), a "Wishlist" page and header link, save/remove controls on product cards and the product detail page, and the `GET /api/v1/wishlist`, `POST /api/v1/wishlist/items`, and `DELETE /api/v1/wishlist/items/{product_id}` endpoints. Adding is idempotent, and every read/write is scoped to the signed-in customer.
- Added an in-app notification inbox: the `notifications` table (revision `20261005_12`), a header bell with an unread badge, the `/notifications` page, and an API (`GET /api/v1/notifications`, `POST /api/v1/notifications/{id}/read`, `POST /api/v1/notifications/read-all`). Customer and seller alerts are created on checkout, customers are notified on order-status and delivery changes, riders on assignment, and sellers on store approval. Notification writes are best-effort and never break the triggering request.
- Fixed the auth "show password" control: the floating-label CSS lifted the password input above the toggle button (input `z-index: 1` vs button auto), so the click never fired. The toggle now stacks above the input, and the reset-password toggles (which render `disabled`) are enabled once JavaScript runs.
- Added product reviews: purchase-verified reviews (a delivered order is required) with 1–5 star ratings and comments, an author-name snapshot, a product-page review list and rating summary, an Admin moderation queue (`POST /admin/reviews/<id>/moderate`), the `reviews` table (revision `20261004_11`), and the `GET|POST /api/v1/products/{id}/reviews` endpoints.
- Added the versioned `/api/v1` JSON API foundation (Bravo-compatible): a consistent success/collection/error envelope, JSON error handlers that never leak internals, shared model serializers, `GET /api/v1/health`, and `GET /api/v1/auth/csrf`.
- Added `GET /health/db` as a dedicated database readiness probe alongside the existing `GET /health`.
- Added Phase 1 Flask application foundation and configuration.
- Added relational user, customer, and admin profile models.
- Added password-hashed customer registration and session authentication.
- Added responsive starter templates and authentication tests.
- Added Phase 2 catalog models, active catalog services, customer routes, search, seed command, responsive food cards, and catalog tests.
- Added lightweight session cart, COD checkout, order/order-item snapshots, customer order history, and protected admin product/category/order controls.
- Added seller-owned multilingual listings, category CRUD, product variants and stock, Admin product moderation, and the fail-closed catalog image pipeline (Phase 3 complete).
- Added Admin one-time-code sign-in: Admin accounts use an emailed single-use code (10-minute expiry, five-attempt lock, one-per-minute resend) instead of a password (revision 20261001_08).
- Admin accounts are bootstrapped from `ADMIN_EMAIL`; `ADMIN_PASSWORD` is no longer used.
- Scoped link hover underlines to auth pages; other site links no longer underline on hover.
- Added order transaction email templates (order received, receipt, order status update, and Admin new-order notification).
- Phase 4 complete: one checkout now creates seller-specific sub-orders with a per-order delivery fee, a localized ReportLab PDF invoice per seller, and a durable email outbox with automatic retry (`flask retry-emails`).
- Phase 5 complete: Admin delivery assignment plus a Rider workflow (assigned → picked up → out for delivery → delivered) with proof of delivery and server-validated state transitions.
- Phase 6 complete: an `audit_events` trail for security-relevant actions, integrity-verified `backup-db`/`restore-db` commands (`flask backup-db --to` / `flask restore-db --from`), a `db-size` check against the `MAX_DATABASE_BYTES` ceiling (400 MiB default), and a `production-check` launch review.
- Account management: customers can delete their own account; the primary Admin (from `ADMIN_EMAIL`) can delete Seller, Rider, and sub-Admin accounts while the primary Admin account stays protected. The Admin sign-in entry point now refuses any email that is not an active Admin account.
- Project-wide cleanup: renamed the session cookie to `nexhaat_session` and the Render blueprint service/database to NexHaat; refreshed the API, DATABASE, SETUP, and ARCHITECTURE docs to cover all six phases; connected the synchronous email path to the shared delivery helper; moved the archived OTP design reference out of the Jinja template tree; dropped redundant `.gitkeep` files; and expanded `.env` with every supported setting.
