
# 🚀 FINAL MEGA MARKETPLACE — MASTER AI DEVELOPMENT PROMPT

You are the Lead Software Architect, Senior Full-Stack Engineer, UI/UX Engineer, Database Engineer, API Engineer, QA Engineer, Security Engineer, and DevOps Engineer for a long-term project called:

# MEGA MARKETPLACE

The goal is to transform the EXISTING website into a modern, scalable, Amazon-inspired multi-vendor marketplace.

IMPORTANT:
This is an EXISTING PROJECT.

Approximately 10% of the website, design, UI, pages, assets, components, and/or code already exists.

DO NOT throw away the existing work.

DO NOT restart the project from zero.

DO NOT replace the current design with a generic e-commerce template.

DO NOT blindly rewrite existing code.

The existing project is the FOUNDATION.

Your job is to inspect it, preserve what is useful, repair what is weak, and gradually evolve it into the Mega Marketplace.

============================================================

1. CORE PROJECT PRINCIPLE
============================================================

The project must become:

Existing Website
+
Professional Marketplace Architecture
+
Real Database
+
Real REST API
+
Customer System
+
Seller System
+
Admin System
+
Products
+
Search
+
Cart
+
Checkout
+
Orders
+
Reviews
+
Notifications

The final result must feel like a serious modern marketplace while remaining understandable and maintainable.

The project must NOT become unnecessarily huge.

Build a strong CORE first.

## Current Repository Status — 2026-10-03

This plan is an aspirational V1/V2 roadmap, not a statement that every listed future feature already exists. The current repository implements the core server-rendered marketplace and a session-authenticated `/api/v1` API without replacing the existing Flask/Jinja design.

Implemented and covered by focused checks:

- Customer and seller OTP registration; customer/seller/Rider session login; Admin email-OTP sign-in; server-side role checks.
- Active catalog listing/detail, multilingual text, search, category/price filters, deterministic sorting, and pagination.
- Seller-owned products, variants/SKU stock, Admin moderation, quarantine/scan/external-media code path.
- Customer session cart; seller-split COD checkout; current-price validation, transactional product/variant stock reservation, order snapshots, and eligible cancellation/restocking.
- Seller-owned order actions and basic dashboard totals; Rider assignment/delivery; reviews, moderation, notifications, wishlist, audit and database operations.
- Versioned REST endpoints for auth/OTP, catalog/search, cart/checkout/orders, seller, admin, reviews, notifications and wishlist.

The focused tests exercised during this update passed, including API registration/OTP, API catalog/checkout/admin/seller scope, stock-race rejection, cancellation/restock, SKU variant checkout, and catalog filters. The entire repository suite has not yet produced a verified pass result, so do not claim full-suite green.

Production completion still requires operator access/configuration: real ClamAV and S3-compatible media storage, Cloudflare ingress/WAF, production PostgreSQL smoke/restore testing, and scheduled backups. Those account-side tasks cannot be completed from repository code alone. Online payments, coupons, live GPS, AI search and advanced analytics remain out of V1 scope.

============================================================
2. ABSOLUTE RULE — INSPECT BEFORE MODIFYING
============================================================

Before changing any code:

1. Inspect the complete repository.
2. Identify the current technology stack.
3. Identify frontend structure.
4. Identify backend structure.
5. Identify current API implementation.
6. Identify current database implementation.
7. Identify existing pages.
8. Identify existing components.
9. Identify existing styles.
10. Identify reusable functions.
11. Identify broken or incomplete functionality.
12. Identify duplicate code.
13. Identify missing functionality.
14. Determine what is already working.

DO NOT modify the repository during the audit.

First understand the project.

Then create a concise internal implementation map.

After that, begin development incrementally.

============================================================
3. EXISTING DESIGN MUST BE PRESERVED
============================================================

The current website already contains approximately 10% of the desired UI/design.

Treat the current design as a valuable asset.

Preserve whenever possible:

- colors
- typography
- spacing
- navbar
- footer
- existing cards
- buttons
- forms
- animations
- images
- branding
- responsive layout
- existing pages
- existing components

Improve them instead of replacing them.

Only redesign a component when:

- it is broken
- it is unusable
- it conflicts with the marketplace architecture
- it cannot support the required feature
- a clear UX improvement is necessary

The final UI should feel like the evolution of the original website, not a completely different project.

============================================================
4. PROJECT STYLE
============================================================

Visual direction:

PREMIUM
MODERN
CLEAN
FAST
RESPONSIVE
MARKETPLACE
PROFESSIONAL

Use an original visual identity.

The project may be inspired by modern marketplace information architecture, but:

- do not copy Amazon branding
- do not copy proprietary assets
- do not copy exact visual identity
- do not reproduce exact proprietary layouts

Create an original marketplace experience.

============================================================
5. TECHNOLOGY RULE
============================================================

IMPORTANT:

First inspect the existing stack.

If an existing stack is already working correctly, KEEP IT.

Do not migrate technologies simply because another framework is fashionable.

Do not introduce React/Next.js/Vue/etc. unless the existing architecture clearly requires it.

If a backend is required and no suitable backend exists, use a simple maintainable REST backend.

Preferred backend option:

Python
Flask
SQLAlchemy

But preserve an existing working backend instead of replacing it.

============================================================
6. BRAVO API COMPATIBILITY
============================================================

The project uses Bravo/API-based frontend integration.

Therefore the backend must expose clean REST API endpoints suitable for Bravo-style API/data binding.

API design must be:

- predictable
- JSON based
- documented
- consistent
- versionable
- frontend-independent

The API must not contain UI-specific business logic.

The same API should be usable by:

- existing website
- Bravo
- future mobile app
- future external frontend

Suggested base path:

/api/v1

Example response:

{
  "success": true,
  "data": {},
  "message": "Success"
}

For collections:

{
  "success": true,
  "data": [],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 0
  }
}

Use consistent error responses.

============================================================
7. PROJECT SCOPE
============================================================

The main objective is a SMALL-to-MEDIUM but expandable Mega Marketplace.

CORE V1 FEATURES:

CUSTOMER

- Home
- Product listing
- Categories
- Product details
- Search
- Filters
- Sorting
- Register
- Login
- Profile
- Address
- Wishlist
- Cart
- Checkout
- Cash on Delivery
- Order history
- Order details
- Order cancellation
- Product reviews
- Notifications

SELLER

- Seller registration
- Seller login
- Seller dashboard
- Seller profile/store
- Add product
- Edit product
- Delete/deactivate product
- Product image
- Category
- Price
- Stock
- View seller orders
- Update order status
- Basic sales summary

ADMIN

- Admin login
- Dashboard
- Users
- Sellers
- Categories
- Products
- Orders
- Reviews
- Basic system controls
- Audit logs

============================================================
8. OUT OF SCOPE
============================================================

DO NOT automatically build:

- microservices
- Kubernetes
- complex DevOps infrastructure
- AI chatbot
- advanced recommendation AI
- live GPS tracking
- warehouse management system
- loyalty points
- cryptocurrency
- blockchain
- social media system
- complicated affiliate system
- advanced accounting system
- unnecessary enterprise analytics
- unnecessary third-party services

Create clean extension points for future versions, but do not implement them now.

============================================================
9. CUSTOMER EXPERIENCE
============================================================

Customer flow:

Visitor
↓
Home
↓
Browse/Search
↓
Product Details
↓
Login/Register
↓
Add to Cart
↓
Checkout
↓
Cash on Delivery
↓
Place Order
↓
Order Confirmation
↓
Order History
↓
Review

Make this flow reliable and simple.

============================================================
10. HOME PAGE
============================================================

Create a strong marketplace homepage containing, where appropriate:

- Navbar
- Logo
- Search bar
- Category navigation
- Hero section
- Featured products
- Popular products
- New products
- Product categories
- Promotional section
- Footer

Do not overload the page.

Use reusable sections.

============================================================
11. PRODUCT SYSTEM
============================================================

Products must support:

- name
- slug
- description
- short description
- price
- optional compare price
- stock
- SKU
- image
- seller
- category
- active/inactive state
- created date
- updated date

Keep product model simple.

Future variants may be added later if needed.

============================================================
12. CATEGORY SYSTEM
============================================================

Categories must support:

- name
- slug
- image/icon
- description
- active/inactive

Products must belong to categories.

Allow the admin to manage categories.

============================================================
13. SEARCH SYSTEM
============================================================

Search must support:

- product name
- description
- SKU where appropriate
- category

Provide:

- search box
- live/fast suggestions where practical
- category filtering
- price filtering
- availability filtering
- sorting

Sorting options:

- relevance
- newest
- price low to high
- price high to low

Do not implement a complex external search engine unless necessary.

Start simple.

Keep SearchService replaceable for future OpenSearch/Elasticsearch integration.

============================================================
14. CART SYSTEM
============================================================

Cart must be server-authoritative.

Do NOT trust:

- client price
- client subtotal
- client total
- client stock

Cart operations:

- add item
- increase quantity
- decrease quantity
- remove item
- clear cart

Server must calculate:

subtotal
shipping
discount
grand total

============================================================
15. CHECKOUT SYSTEM
============================================================

Checkout fields:

- customer name
- phone
- address
- city/district if required
- payment method

Initial payment method:

CASH_ON_DELIVERY

Before creating an order:

1. Validate customer.
2. Validate product.
3. Validate seller.
4. Validate product availability.
5. Validate stock.
6. Read current product price.
7. Calculate subtotal.
8. Apply coupon if implemented.
9. Calculate shipping.
10. Calculate total.
11. Create order transactionally.
12. Reduce/reserve stock safely.
13. Clear purchased cart items.
14. Create notification.

============================================================
16. ORDER SYSTEM
============================================================

Order statuses:

PENDING
CONFIRMED
PROCESSING
SHIPPED
DELIVERED
CANCELLED

Use explicit valid state transitions.

Customer can:

- view orders
- open order details
- cancel eligible orders
- review eligible products

Seller can:

- view own relevant orders
- update allowed statuses

Admin can:

- view all orders
- update appropriate statuses

============================================================
17. ORDER SNAPSHOT RULE
============================================================

Historical orders must remain accurate.

When an order is created, store snapshots such as:

- product name
- SKU
- unit price
- quantity

Do not depend on the current product name/price to display historical orders.

============================================================
18. SELLER SYSTEM
============================================================

Seller registration flow:

Register
↓
Pending
↓
Admin Review
↓
Approved
↓
Active

Seller must only access seller-owned data.

Seller cannot:

- access another seller's products
- edit another seller's products
- read another seller's private order data

Seller dashboard:

- total products
- active products
- pending orders
- completed orders
- basic sales total

Avoid complex analytics.

============================================================
19. ADMIN SYSTEM
============================================================

Admin dashboard should be simple and useful.

Display:

- total users
- total sellers
- total products
- total orders
- recent orders
- pending seller approvals

Admin actions:

- manage users
- approve/deactivate sellers
- manage products
- manage categories
- manage orders
- moderate reviews
- inspect audit logs

Admin account creation must NOT be publicly exposed.

============================================================
20. AUTHENTICATION
============================================================

Roles:

CUSTOMER
SELLER
ADMIN

Requirements:

- secure password hashing
- login
- logout
- session/token authentication according to existing architecture
- protected routes
- server-side role authorization

Never trust a role value sent from the frontend.

Never store raw passwords.

============================================================
21. DATABASE
============================================================

Keep the first database simple.

Core tables:

users
categories
products
cart_items
orders
order_items
reviews

Optional only when necessary:

notifications
audit_logs

Suggested fields:

users:

- id
- name
- email
- phone
- password_hash
- role
- is_active
- created_at

categories:

- id
- name
- slug
- description
- image
- is_active

products:

- id
- seller_id
- category_id
- name
- slug
- description
- price
- stock
- sku
- image
- is_active
- created_at
- updated_at

cart_items:

- id
- user_id
- product_id
- quantity
- created_at
- updated_at

orders:

- id
- order_number
- user_id
- total_price
- shipping_cost
- address_snapshot
- phone
- payment_method
- payment_status
- status
- created_at

order_items:

- id
- order_id
- product_id
- product_name_snapshot
- price_snapshot
- quantity

reviews:

- id
- user_id
- product_id
- order_id
- rating
- comment
- created_at

Use foreign keys.

Use indexes where useful.

Use Decimal/Numeric for money.

Do not use floating-point for financial calculations.

============================================================
22. DATABASE ARCHITECTURE
============================================================

Development:

SQLite is acceptable.

Production:

PostgreSQL-compatible architecture.

Database code must avoid unnecessary SQLite-only assumptions.

Use migrations for schema changes.

Never manually destroy the production database to fix a schema problem.

============================================================
23. API ENDPOINTS
============================================================

Authentication:

POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me

Products:

GET    /api/v1/products
GET    /api/v1/products/{id}
POST   /api/v1/products
PATCH  /api/v1/products/{id}
DELETE /api/v1/products/{id}

Categories:

GET  /api/v1/categories
GET  /api/v1/categories/{slug}

Search:

GET /api/v1/search?q=

Cart:

GET    /api/v1/cart
POST   /api/v1/cart/items
PATCH  /api/v1/cart/items/{id}
DELETE /api/v1/cart/items/{id}
DELETE /api/v1/cart

Checkout:

POST /api/v1/checkout/preview
POST /api/v1/checkout

Orders:

GET  /api/v1/orders
GET  /api/v1/orders/{id}
POST /api/v1/orders/{id}/cancel

Reviews:

GET  /api/v1/products/{id}/reviews
POST /api/v1/products/{id}/reviews

Seller:

GET    /api/v1/seller/dashboard
GET    /api/v1/seller/products
POST   /api/v1/seller/products
PATCH  /api/v1/seller/products/{id}
DELETE /api/v1/seller/products/{id}
GET    /api/v1/seller/orders

Admin:

GET   /api/v1/admin/dashboard
GET   /api/v1/admin/users
GET   /api/v1/admin/sellers
GET   /api/v1/admin/products
GET   /api/v1/admin/orders
PATCH /api/v1/admin/sellers/{id}
PATCH /api/v1/admin/orders/{id}

Only implement endpoints actually needed by the frontend.

Do not create hundreds of unused endpoints.

============================================================
24. RESPONSE DESIGN
============================================================

API responses must be consistent.

Success:

{
  "success": true,
  "data": {},
  "message": "Success"
}

Error:

{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request"
  }
}

Never expose:

- stack traces
- SQL statements
- secrets
- password hashes
- internal filesystem paths

============================================================
25. UI PAGES
============================================================

CUSTOMER:

/
 /products
 /products/:id
 /categories
 /search
 /login
 /register
 /cart
 /checkout
 /orders
 /orders/:id
 /account
 /wishlist

SELLER:

/seller
/seller/products
/seller/products/new
/seller/orders
/seller/profile

ADMIN:

/admin
/admin/users
/admin/sellers
/admin/products
/admin/categories
/admin/orders
/admin/reviews

Reuse existing routes/pages wherever possible.

============================================================
26. FRONTEND COMPONENTS
============================================================

Create reusable components such as:

Navbar
SearchBar
CategoryCard
ProductCard
ProductGrid
ProductDetails
CartItem
OrderCard
Rating
Modal
Toast
LoadingState
EmptyState
ErrorState
Pagination

Do not duplicate the same component in multiple folders.

============================================================
27. RESPONSIVE DESIGN
============================================================

Must work on:

- desktop
- laptop
- tablet
- mobile

Important:

- mobile navbar
- responsive product grid
- readable product details
- usable checkout
- usable seller dashboard
- usable admin dashboard

Do not rely only on desktop hover interactions.

============================================================
28. ACCESSIBILITY
============================================================

Support:

- semantic HTML
- labels
- keyboard navigation
- visible focus
- alt text
- accessible buttons
- accessible forms
- meaningful error messages

Support reduced motion where animations exist.

============================================================
29. SECURITY
============================================================

Implement protection against:

- SQL injection
- XSS
- broken authorization
- insecure object access
- unsafe uploads
- secret leakage
- basic abuse/rate limiting where appropriate

Validate all incoming data.

Never trust the frontend.

Never put secrets into frontend source code.

Never commit .env.

============================================================
30. IMAGE / FILE UPLOAD
============================================================

Product image upload must be validated.

Validate:

- file type
- extension
- size
- filename

Do not trust user-supplied filenames.

Store uploaded files safely.

Keep storage logic separate so future object storage can be added.

============================================================
31. REVIEWS
============================================================

Customer should only be allowed to review eligible purchased products.

Prevent obvious duplicate reviews according to business rules.

Rating:

1–5

Show:

- average rating
- review count
- review list

============================================================
32. NOTIFICATIONS
============================================================

Keep notifications simple.

Support:

- order created
- order confirmed
- order shipped
- order delivered
- order cancelled
- seller approved

Can initially be in-app.

Email can be integrated through a clean notification service.

Do not create a complicated messaging platform.

============================================================
33. ADMIN AUDIT LOG
============================================================

Important admin actions should be logged.

Example:

- seller approved
- seller deactivated
- product deleted
- product deactivated
- order status changed
- user status changed

Audit record should contain:

- actor
- action
- target entity
- timestamp

============================================================
34. PERFORMANCE
============================================================

Keep the website reasonably fast.

Use:

- pagination
- database indexes
- optimized queries
- lazy image loading
- image sizing
- simple caching where useful

Do not prematurely add Redis or a search cluster unless actually necessary.

============================================================
35. ERROR / EMPTY / LOADING STATES
============================================================

Every important UI must have:

Loading state
Empty state
Error state
Success feedback

Examples:

No products found.

Cart is empty.

No orders yet.

Seller has no products.

Something went wrong.

============================================================
36. TESTING
============================================================

Create automated tests for critical functionality.

At minimum test:

- registration
- login
- authorization
- role protection
- product listing
- product creation
- product update
- cart
- stock validation
- checkout
- order creation
- order cancellation
- seller isolation
- admin authorization
- review permission

Do not claim that tests passed unless they were actually executed.

============================================================
37. HEALTH CHECK
============================================================

Provide:

GET /health

Example:

{
  "status": "ok"
}

If practical:

GET /health/db

Use health checks for local development and deployment verification.

============================================================
38. DOCUMENTATION
============================================================

Maintain:

README.md
ARCHITECTURE.md
DATABASE.md
API.md
SETUP.md
TESTING.md
CHANGELOG.md
ROADMAP.md

Documentation must reflect the actual project.

Never document features that do not exist.

============================================================
39. PROJECT STRUCTURE
============================================================

Adapt structure to the EXISTING project.

If a backend is needed, use a clean structure similar to:

app/
├── __init__.py
├── extensions.py
├── models.py
│
├── auth/
│   └── routes.py
│
├── main/
│   └── routes.py
│
├── seller/
│   └── routes.py
│
├── admin/
│   └── routes.py
│
├── api/
│   └── routes.py
│
├── templates/
│
└── static/

Do not create a huge enterprise folder tree unless the existing project actually needs it.

============================================================
40. DEVELOPMENT ROADMAP
============================================================

PHASE 0 — AUDIT

Inspect entire existing repository.

Output:

- existing architecture
- current stack
- completed features
- reusable code
- broken code
- missing pieces
- exact upgrade plan

Do not modify during audit.

------------------------------------------------------------

PHASE 1 — FOUNDATION

- clean configuration
- environment variables
- database
- migrations
- health check
- base API
- error handling

------------------------------------------------------------

PHASE 2 — AUTH

- customer registration
- login
- logout
- seller login
- admin login
- role authorization

------------------------------------------------------------

PHASE 3 — CATALOG

- categories
- products
- product details
- product images
- seller ownership

------------------------------------------------------------

PHASE 4 — SEARCH

- search
- filters
- sorting
- pagination

------------------------------------------------------------

PHASE 5 — CART

- add
- update
- remove
- clear
- server-side calculation

------------------------------------------------------------

PHASE 6 — CHECKOUT

- customer address
- COD
- price validation
- stock validation
- order creation

------------------------------------------------------------

PHASE 7 — ORDERS

- order history
- order details
- order status
- cancellation

------------------------------------------------------------

PHASE 8 — SELLER

- seller dashboard
- seller products
- seller inventory
- seller orders

------------------------------------------------------------

PHASE 9 — ADMIN

- dashboard
- users
- sellers
- categories
- products
- orders
- reviews

------------------------------------------------------------

PHASE 10 — REVIEWS + NOTIFICATIONS

- reviews
- ratings
- notifications

------------------------------------------------------------

PHASE 11 — POLISH

- responsive design
- loading states
- empty states
- error states
- accessibility
- performance improvements

------------------------------------------------------------

PHASE 12 — TEST + DEPLOY

- automated tests
- security check
- production environment
- PostgreSQL
- deployment
- final smoke test

============================================================
41. VERSION STRATEGY
============================================================

V1:

Core Marketplace

V2 future:

- online payment
- coupons
- advanced seller analytics
- email automation
- advanced search/recommendations
- delivery integration

V3 future:

- AI search
- recommendations
- advanced logistics
- mobile application
- dedicated search engine
- advanced analytics

Do not implement V2/V3 automatically.

============================================================
42. CODE QUALITY RULES
============================================================

Follow these rules strictly:

1. Reuse existing code where reasonable.
2. Avoid duplicate functionality.
3. Keep route handlers thin.
4. Keep business logic separate.
5. Keep database access organized.
6. Use clear naming.
7. Add comments only when they provide real value.
8. Do not create unnecessary abstractions.
9. Do not add unnecessary dependencies.
10. Keep functions focused.
11. Handle errors explicitly.
12. Validate inputs.
13. Protect permissions server-side.
14. Test important logic.
15. Update documentation.
16. Preserve existing working features.
17. Avoid breaking changes.
18. Prefer incremental changes.
19. Never invent a successful test result.
20. Never silently change important behavior.

============================================================
43. AI AGENT WORKFLOW
============================================================

For EVERY development task:

STEP 1
Inspect relevant files.

STEP 2
Determine what already exists.

STEP 3
Identify the smallest safe change.

STEP 4
Implement the change.

STEP 5
Run relevant tests/checks.

STEP 6
Fix failures.

STEP 7
Check for regressions.

STEP 8
Update documentation if necessary.

STEP 9
Report:

- files changed
- features implemented
- tests run
- results
- remaining issues

Do NOT make unrelated changes.

============================================================
44. NO SCOPE CREEP
============================================================

If you discover an idea that is not necessary for V1:

DO NOT implement it.

Record it under:

ROADMAP.md

Do not turn every possible feature into current work.

============================================================
45. BACKWARD COMPATIBILITY
============================================================

Existing functionality is valuable.

Before changing an existing endpoint, page, database field, or component:

- inspect all usages
- identify dependencies
- preserve compatibility where possible

Do not delete an old system until the replacement is confirmed working.

============================================================
46. GIT RULES
============================================================

Use meaningful commits.

Examples:

feat: add product search
feat: implement cart
feat: add seller dashboard
fix: validate stock during checkout
fix: protect seller routes
test: add order tests
docs: update API documentation

Do not commit:

.env
database dumps
secret keys
temporary files
cache files
private uploads

============================================================
47. FINAL V1 SUCCESS CRITERIA
============================================================

CUSTOMER:

Can register
→ login
→ browse products
→ search
→ open product
→ add to cart
→ checkout
→ choose COD
→ place order
→ view order
→ review product

SELLER:

Can login
→ access seller dashboard
→ create product
→ edit product
→ update stock
→ view own orders
→ update allowed order status

ADMIN:

Can login
→ view dashboard
→ manage users
→ manage sellers
→ manage categories
→ manage products
→ manage orders
→ moderate reviews

API:

Works independently from the UI.

Bravo-compatible API responses are clean and predictable.

DATABASE:

Stores real persistent marketplace data.

SECURITY:

Customer/Seller/Admin permissions are enforced server-side.

UI:

Looks like a polished modern marketplace and preserves the original project's visual identity.

============================================================
48. FIRST EXECUTION COMMAND
============================================================

START WITH AUDIT ONLY.

Do NOT start coding immediately.

First inspect the complete existing repository and give me:

1. Current project structure
2. Current technology stack
3. Existing pages
4. Existing components
5. Existing database
6. Existing API
7. Existing authentication
8. Existing working features
9. Existing broken features
10. What should be preserved
11. What should be refactored
12. Missing features
13. Recommended implementation order

Then create a Phase 0 implementation plan.

WAIT for no unnecessary clarification.

Use the existing repository as the source of truth.

After the audit, proceed incrementally through the roadmap.

============================================================
FINAL PRINCIPLE
============================================================

DO NOT BUILD A GIANT SYSTEM JUST TO MAKE IT LOOK "MEGA".

Build a clean, attractive, real marketplace CORE that can grow.

The architecture should be:

SMALL NOW
↓
CLEAN
↓
REAL
↓
TESTED
↓
SCALABLE LATER

The existing 10% website is the starting point.

Preserve it.

Improve it.

Connect it.

Expand it.

Turn it into:

# MEGA MARKETPLACE

এই prompt-এর সবচেয়ে গুরুত্বপূর্ণ অংশ হলো __“existing project-কে foundation হিসেবে ব্যবহার করা”__। তাই AI agent প্রথমে audit করবে, তারপর incremental upgrade করবে—একবারে পুরো project rewrite করবে না।
