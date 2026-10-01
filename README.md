# NexHaat Marketplace

NexHaat is being developed in reviewed phases as a multilingual marketplace for customers, sellers, delivery riders, and administrators. **Phase 1, Phase 2, and Phase 3 are complete.** Phase 3 delivered seller-owned product listings, inventory variants, optional multilingual product text, Admin moderation, and a fail-closed catalog image pipeline. Checkout, rider operations, and production launch remain behind their phase review gates.

## Phase plan

1. **Authentication, brand, and language foundation** — integrated Login and Sign Up experience, NexHaat branding and favicon, accessible responsive forms, CSRF protection, password reset, and four-language support.
2. **Roles and dashboards** — customer, seller, rider, and admin permissions with approval-based account creation where required.
3. **Seller and admin catalog** — store onboarding, product and food categories, variants, stock, moderation, and seller-provided translations.
4. **Customer checkout, invoices, and email** — multi-seller checkout, seller-specific orders and invoices, initially with cash on delivery.
5. **Rider and delivery operations** — delivery assignment, pickup and delivery states, and proof of delivery.
6. **Security and production launch** — WAF/firewall configuration, production review of upload scanning, backups, restore checks, and release review.

Complete and review each phase before beginning the next one.

## Languages

The interface starts in **English (US)** and supports **বাংলা**, **हिन्दी**, and **العربية**. Arabic pages use right-to-left direction. Anonymous language choices live in the signed session; signed-in preferences are stored on the user account. Locale resolution is account preference, explicit session choice, browser language, then English (US).

Phase 1 and 2 translate shared navigation, authentication and password recovery, role dashboards, seller review, staff invitations, and password and invitation email. Phase 3 adds translated catalog, seller inventory, and catalog moderation screens. Remaining checkout and order workflows will be translated in Phase 4. Seller-authored product text is not machine translated; missing translations retain the original wording and language label.

Translation catalogs live in `app/translations/<locale>/LC_MESSAGES/messages.po`. Extract and update them after adding translatable interface strings:

```powershell
pybabel extract -F babel.cfg -k gettext -k lazy_gettext -k _ -o app/translations/messages.pot app
pybabel update -i app/translations/messages.pot -d app/translations
```

Review and translate the `.po` files, then compile them:

```powershell
pybabel compile -d app/translations
```

The Render build compiles these catalogs after installing the application dependencies.

## Local setup

1. Create and activate a virtual environment: `python -m venv .venv`
2. Install packages: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and set a random `SECRET_KEY`. Keep `.env` out of source control.
4. Apply database migrations: `flask --app run.py db upgrade`
5. Start the development server in the foreground: `flask --app app run --host 127.0.0.1 --port 5009`. Keep its output in the terminal; do not redirect stdout or stderr to files.

Run the automated checks with `python -m pytest`. SQLite is the local default; deployment uses PostgreSQL through `DATABASE_URL`.

## Phase 1 details

- Flask/Jinja customer login and registration use the integrated neumorphic flip-card design with a mobile layout, keyboard support, and reduced-motion handling.
- Customer sign-up checks password confirmation on both client and server. Forms use CSRF tokens, server-side validation, password hashing, and the existing login throttling and password-reset protections.
- Admin accounts are provisioned through `ADMIN_EMAIL`, the `create-admin` CLI, or a staff invitation, and use email OTP sign-in instead of passwords.
- Language changes use `POST /language`, validate supported locales, preserve a safe same-site redirect, and require a CSRF token.
- User language preference is an additive nullable database field. The migration also updates the old default FreshBite brand setting to NexHaat.
- Uploaded images remain outside the database. Reference data imports enforce the separate 400 MB database cap.

## Phase 2 details

- Customers, sellers, and riders use `/auth/login`; Admins use `/admin/login` and verify a one-time code sent to their account email before entering operations.
- Customers can self-register. Seller applications create a restricted pending seller account; Admin can approve or reject each application. Product publishing remains reserved for Phase 3.
- Admin can invite Riders and additional Admins. Setup links expire after 24 hours, are one-use, and store only a keyed token digest. Riders choose a password; invited Admins activate their account and use email OTP for sign-in.
- Admin OTP and staff invitations require BREVO_API_KEY and MAIL_DEFAULT_SENDER; invitations also require a canonical HTTPS PUBLIC_BASE_URL in production. Admin codes expire after 10 minutes, allow five attempts, and can be resent once per minute.
- Set `ADMIN_EMAIL` to bootstrap the primary Admin. Local development creates it automatically; after production database migrations, run `flask --app run.py ensure-admin` once.
- Forgot Password works for active non-Admin accounts with the same non-enumerating response and single-use verification-code protections.
- Marketplace customer cart and account actions reject signed-in Seller, Rider, and Admin roles. Admin review routes are protected by role and CSRF checks.
- The portal and operations screens follow the supplied neumorphic login reference with responsive cards, focus states, floating shapes, and reduced-motion handling. Arabic uses the same RTL direction as the shared layout.
- Revision 20261001_08 adds server-side Admin login challenge storage. Run `flask --app run.py db upgrade` before starting a previously initialized local database.

## Phase 3 complete

- Approved sellers can create and update their own listings, maintain base and SKU-variant stock, and provide product names and descriptions in supported languages. Each new or edited listing waits for Admin approval before appearing publicly. Category CRUD, localized storefront search, and seller ownership checks are included.
- Admin can approve or reject seller product submissions with a review note. Active storefront queries exclude pending listings; translated text is used when present and otherwise the source language is identified. Phase 3 catalog and inventory screens have Bengali, Hindi, and Arabic translations.
- Product images use a fail-closed pipeline: private quarantine, ClamAV CLI scan, JPEG/PNG/WEBP decoding and sanitizing, then upload to an S3-compatible bucket. A rejected or unscanned image stays outside public storage. The app returns an image URL only after external storage succeeds.
- To enable image publishing, install a ClamAV command (`clamdscan` by default; set `CATALOG_VIRUS_SCANNER` to another compatible executable if needed) in the app runtime. Set `CATALOG_MEDIA_BUCKET`, `CATALOG_MEDIA_REGION`, `CATALOG_MEDIA_PUBLIC_BASE_URL`, and, for S3-compatible storage, `CATALOG_MEDIA_ENDPOINT_URL`; provide credentials through the AWS SDK credential chain. The public URL host must be served by the configured bucket/CDN. Until scanner and storage are configured, image uploads are intentionally rejected. Configure these values as private service environment settings in deployment.
- Defaults: 3 MB per image, 40 million pixels, 100 MB total quarantine, and 24-hour quarantine retention. Override with the `MAX_CATALOG_*` and `CATALOG_QUARANTINE_*` settings as needed.
- The catalog seed supplies a small curated food, grocery, and retail category set. It does not generate pretend food listings or prices. USDA reference foods remain labeled as reference data until a seller publishes a priced, reviewed listing.
- Revision 20260929_07 adds seller ownership, product stock and review metadata, product translation records, and product variant records. Phase 3 is complete: the full test suite passes, and only the deployment-side scanner and storage configuration remains before live image publishing. Checkout variant selection and stock deduction are planned for Phase 4.

## Deployment

The project includes a production entry point, a `Procfile`, and a Render blueprint. The blueprint builds Python dependencies and translation catalogs, applies migrations before serving traffic, initializes the admin account, and seeds the catalog. Configure a strong secret, managed PostgreSQL URL, Brevo API key, sender address, canonical HTTPS `PUBLIC_BASE_URL`, and any admin bootstrap values using the host's private environment settings.

The Phase 6 design proposes Cloudflare WAF and Tunnel in front of a private Render service. That external account and network configuration is not enabled by this Phase 2 code change. Security uses layered controls; no application can promise to be impossible to hack.
