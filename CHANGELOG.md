# Changelog

## Unreleased

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
