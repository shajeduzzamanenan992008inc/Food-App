# API and route conventions

Phase 1 currently exposes:

- `GET /` — starter home page
- `GET|POST /auth/register` — customer registration
- `GET|POST /auth/login` — session login
- `POST /auth/logout` — session logout
- `GET /menu?page=<number>` — paginated active customer catalog
- `GET /category/<slug>?page=<number>` — paginated active category products
- `GET /food/<slug>` — available product detail
- `GET /search?q=<term>&page=<number>` — bounded, paginated case-insensitive search across available product name and description
- `GET /api/search-suggestions?q=<term>` — up to eight bounded catalog suggestions
- `GET /health` — database readiness status without exposing connection details
- `GET /cart` — current session cart
- `POST /cart/add/<product_id>` — add an available product
- `POST /cart/update` — update session quantities
- `POST /cart/remove/<product_id>` — remove a cart item
- `GET|POST /checkout` — COD checkout and order creation
- `GET /orders/<order_number>` — order confirmation
- `GET /my-orders` — logged-in customer order history
- `GET /admin` — admin product, category, and order controls
- `GET|POST /admin/login` — administrator-only sign-in entry point

Future JSON endpoints should return consistent success/error envelopes, validate input at the boundary, and never trust prices, availability, roles, or totals supplied by a browser.
