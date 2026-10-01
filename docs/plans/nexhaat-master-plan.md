# NexHaat: সমন্বিত Master Plan

## ১. উদ্দেশ্য ও কাজের পদ্ধতি

NexHaat হবে Customer, Seller, Rider ও Admin-এর জন্য একটি modular, multilingual marketplace। কাজ ছয়টি phase-এ এগোবে। প্রতিটি phase আলাদাভাবে বাস্তবায়ন, পরীক্ষা, review ও acceptance পাবে; acceptance-এর আগে পরের phase শুরু হবে না।

এই নথিতে পূর্ববর্তী `nexhaat-master-plan.md`, `PLAN.md` ও `PLANE 1.md`-এর পরিকল্পনা একত্র করা হয়েছে; এটিই এখন canonical merged plan। উৎসের requirement-গুলো পরিকল্পনার বিষয়বস্তু; সেগুলো নিজে থেকে application code, database data/schema, migration বা production configuration পরিবর্তনের অনুমতি নয়।

### বর্তমান stage status — 2026-10-01

- **Phase 1 — সম্পূর্ণ।** Authentication, language foundation ও সংশ্লিষ্ট acceptance review সম্পন্ন।
- **Phase 2 — সম্পূর্ণ।** Role dashboards ও access-control acceptance review সম্পন্ন।
- **Phase 3 — সম্পূর্ণ (code, test ও acceptance review)।** Seller catalog, product variant, stock, Admin moderation, seller-authored multilingual text এবং fail-closed media pipeline বাস্তবায়িত; পূর্ণ regression suite পাস করেছে (58 passed)। শুধু live image publish-এর জন্য deployment-এ ClamAV executable এবং S3-compatible bucket/CDN configuration দরকার।
- **সম্পূর্ণ stage: 3/6।** পরবর্তী কাজ: deployment-এ media scanner/storage configuration দিয়ে clean/rejected upload live smoke check চালিয়ে Phase 3-এর deployment ধাপ সম্পন্ন করা, তারপর Phase 4 — multi-vendor cart, seller-specific invoice ও localized order email।

### ভাষা ও localization

- সমর্থিত locale: English (US) — **en_US**, বাংলা — **bn_BD**, हिन्दी — **hi_IN**, العربية — **ar**।
- নতুন বা অন্য কোনো পছন্দ সংরক্ষিত নেই এমন ভিজিটরের default web language হবে **English (US), en_US**।
- ভাষা নির্ধারণের অগ্রাধিকার: saved account preference → explicit session selection → browser language → en_US fallback।
- Signed-in ব্যবহারকারীর নির্বাচিত ভাষা account preference-এ এবং anonymous ব্যবহারকারীর নির্বাচন session-এ সংরক্ষিত হবে।
- Arabic-এর জন্য form, navigation, alignment, spacing, icons, validation ও motion-সহ পূর্ণাঙ্গ RTL সমর্থন থাকবে। CSS logical properties ব্যবহার করা হবে।
- UI ও system text translation catalog থেকে আসবে। Seller-এর লেখা স্বয়ংক্রিয়ভাবে machine-translate হবে না। অনুবাদ অনুপস্থিত থাকলে original text ও তার ভাষা চিহ্নিত করে দেখাতে হবে।

### স্থাপত্যের লক্ষ্য

প্রস্তাবিত logical flow:

    Browser
      → CDN/WAF ও application ingress
      → Flask application ও role-based Blueprints
      → service layer
      → PostgreSQL/Supabase

Image ও file database-এর বাইরে external storage-এ থাকবে। Cloudflare WAF/Tunnel এবং Render private networking প্রস্তাবিত production target; এই topology provider documentation থেকে নেওয়া architectural inference, তাই deployment path feasibility ও account tier যাচাইয়ের পর স্থির হবে। [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/), [Render private services](https://render.com/docs/private-services), [Render private network](https://render.com/docs/private-network/), [Cloudflare managed rules](https://developers.cloudflare.com/waf/managed-rules/).

## ২. ভাগ করা স্থাপত্য ও নিরাপত্তা শর্ত

### Authentication UI ও component boundary

README-তে live implementation-এর স্থান হিসেবে উল্লেখ আছে:

- app/templates/auth/_auth_card.html
- app/templates/auth/base.html
- app/static/css/auth.css
- app/static/js/auth.js

Archived index.html, style.css ও script.js কেবল design reference হিসেবে থাকবে; মূল app সেগুলো সরাসরি serve করবে না। Auth experience-এ Login ও Sign Up, brand hierarchy, password visibility, inline validation, loading/error/success feedback এবং keyboard navigation থাকবে। Split-screen 3D/glass/neumorphic presentation মার্জিত ও responsive হবে; ছোট পর্দায় visual panel সরল বা collapse হতে পারে।

Component-এর দায়িত্ব:

- _auth_card.html: login/sign-up form, CSRF field, field-level/server-rendered errors, password control, translation keys ও submit state।
- base.html: shared layout, brand/background, language selector, accessibility hooks ও flash messages।
- auth.css: design tokens, layout, responsive states, 3D/neumorphic surfaces, RTL ও reduced-motion support।
- auth.js: password visibility, mode transition, progressive client validation ও loading enhancement। JavaScript server-side validation বা security decision-এর বিকল্প হবে না।

Motion অল্প ও উদ্দেশ্যপূর্ণ হবে, interaction আটকে দেবে না এবং prefers-reduced-motion মানবে। Animation একা কোনো error বা success state বোঝানোর মাধ্যম হবে না। Form field-এ semantic label, visible focus, logical tab order, accessible status announcement এবং error-to-field association থাকতে হবে।

### Validation, sessions ও error handling

- Client-side feedback progressive enhancement; server-side validation authoritative।
- Field states: idle, focus, valid, invalid, pending (শুধু বাস্তব async কাজ থাকলে) ও disabled।
- CSRF protection login/sign-up এবং language পরিবর্তনের POST route-এ থাকবে।
- Secure password hashing, session/cookie configuration, input validation, output escaping, safe redirect handling ও duplicate submission প্রতিরোধ থাকবে।
- Error feedback-এ validation, authentication failure, expired session, network/server failure ও rate limit-এর জন্য স্পষ্ট recovery path থাকবে; internal sensitive details প্রকাশ পাবে না।
- Auth interface কম resource ব্যবহার করবে; heavy blur/3D effects কম ক্ষমতার device-এ gracefulভাবে degrade করবে।

### Role ও account provisioning

চারটি role: customer, seller, rider, admin। Role-to-dashboard redirect কেন্দ্রীয় mapping দিয়ে হবে। Role permissions, route authorization ও seller data isolation server-side enforce হবে; UI visibility একমাত্র access control হবে না।

- Customer সরাসরি sign up করতে পারবে।
- Seller application দেবে; Admin approval-এর পর seller capabilities পাবে।
- Rider ও Admin account Admin তৈরি করবে বা invite করবে।
- User model-এর source proposal-এ id, role, email, password_hash, locale_preference (default en_US) ও 2fa_enabled আছে। বর্তমান schema পর্যালোচনা ও migration plan ছাড়া এই প্রস্তাবকে সরাসরি database migration ধরা হবে না।

### Catalog, media ও database

Database implementation-এ repository model ও Alembic migration-ই source of truth। Local default SQLite; deployment `DATABASE_URL` দিয়ে PostgreSQL ব্যবহার করে। 2026-10-01 repository review-তে local migration chain-এর current revision `20260929_07` ছিল। PostgreSQL/Supabase deployment proposal বাস্তব quota, backup ও monitoring যাচাইয়ের পরেই স্থির হবে।

Source plans-এ থাকা নিচের schema shape-গুলো **design proposal**, বর্তমান schema-র নিশ্চয়তা নয়:

```text
User: id, role, email, password_hash, locale_preference, 2fa_enabled
Product: id, seller_id, category_id, price_bdt, stock, status,
         title_translations JSONB, desc_translations JSONB
```

Translation JSONB হলে locale অনুযায়ী content দেখাতে হবে; translation না থাকলে original text এবং তার language label দেখাতে হবে। এই proposal বাস্তবায়নের আগে বর্তমান model/schema review ও migration plan দরকার।

- Database সর্বোচ্চ 400 MB-এর মধ্যে রাখতে হবে; provider quota, size monitoring, backup ও restore behavior যাচাই করতে হবে।
- Image/file database-এ রাখা হবে না; validated media approved external storage-এ থাকবে।
- Upload approval flow: quarantine → private antivirus scan ও validation → approved external storage। Scan/validation শেষ হওয়ার আগে upload normal application storage-এ যাবে না।
- Capacity বা row-count দেখানোর জন্য duplicate/fake data তৈরি করা যাবে না; food/category data যাচাইযোগ্য ও বাস্তব হতে হবে।

### Security, configuration ও observability

- Login throttling, Admin MFA, audit logging, dependency checks এবং role/seller data isolation থাকবে।
- Cloudflare WAF managed rules-এর সুনির্দিষ্ট availability account tier-এর ওপর নির্ভর করবে।
- Production secrets environment/configuration store-এ থাকবে; source code বা Git-এ নয়।
- Password, password hash, session secret, CSRF token বা credential log করা যাবে না।
- Structured diagnostic events: login success/failure, logout, registration, role resolution failure, authorization denial, rate limit, language change ও server error।
- Layered defense ব্যবহার হবে; কোনো security layer-কে সম্পূর্ণ hack-proof ধরে নেওয়া হবে না।

## ৩. ছয়টি implementation phase

### Phase 1 — Foundation, Authentication ও i18n

**Deliverables**

- Flask-Login-ভিত্তিক login/sign-up, CSRF ও authoritative server validation।
- Neumorphic/3D-inspired responsive auth UI, keyboard/accessibility states, RTL এবং reduced-motion behavior।
- Flask-Babel translation catalog ও locale selector ([Flask-Babel documentation](https://python-babel.github.io/flask-babel/))।
- CSRF-protected POST /language; account/session preference persistence এবং browser fallback।
- Auth component-এ সব user-facing text translation catalog-এ রাখা।

**Acceptance gate**

- Login, sign-up, logout, CSRF, server validation ও session behavior কাজ করে।
- en_US default-সহ চারটি locale UI-তে কাজ করে; preference persistence ও fallback সঠিক।
- Arabic RTL, responsive view, keyboard/focus/error association এবং reduced-motion ব্যবহারযোগ্য।
- Loading, error, success ও rate-limited state স্পষ্ট এবং accessible।
- Backward compatibility review-এ বিদ্যমান route, translation key বা behavior অকারণে ভাঙেনি; প্রয়োজনীয় schema change-এর migration plan আছে।

**Repository verification note**

README-তে উপরের চারটি live auth path ইতিমধ্যে integrated বলা হয়েছিল, কিন্তু Phase 1 শুরুর সময় checkout-এ সেগুলো অনুপস্থিত ছিল। Phase 1-এ auth template, static asset ও সংশ্লিষ্ট email template পুনরায় যোগ করা হয়েছে; README-র সঙ্গে repository status এখন সামঞ্জস্যপূর্ণ।

**Acceptance review (2026-10-01)**

Flask-Login active-user ও `auth_version` যাচাইসহ wired হয়েছে; shared role decorators server-side permission enforcement করে। Auth, locale, CSRF, role routing, seller isolation এবং customer-to-admin denial-এর focused regression set পাস করেছে: **28 passed**। Fresh temporary SQLite database-এ migration chain `20260929_07` পর্যন্ত সফল হয়েছে। Auth CSS/template review-তে responsive breakpoints, keyboard focus, field error association, Arabic RTL এবং reduced-motion rules পাওয়া গেছে। Local HTTP smoke-এ `/health`, `/auth/login` এবং auth CSS—তিনটিই `200` দিয়েছে।

### Phase 2 — Role dashboards ও access control

**Deliverables**

- Admin, Seller, Rider ও Customer-এর জন্য পৃথক Flask Blueprint ও dashboard।
- Central role-to-dashboard mapping, RBAC decorator/permission checks এবং seller-scoped data isolation।
- Customer self-signup, Seller application/admin approval, এবং Admin-controlled Rider/Admin provisioning।

**Acceptance gate**

- প্রতিটি role সঠিক dashboard-এ যায়।
- ভুল role-এর route access প্রত্যাখ্যাত হয়; customer Admin area পায় না, Rider Seller/Admin access পায় না।
- Seller-রা অন্য Seller-এর data পড়তে বা পরিবর্তন করতে পারে না।
- Privileged action Admin control-এর অধীনে এবং route-level authorization server-side যাচাই করা।

**Repository implementation note (2026-09-30)**

Phase 2-এ চার role-এর dashboard endpoint ও central role-to-dashboard map যোগ হয়েছে। Shared role authorization এখন customer, seller, rider ও admin routes-এ ব্যবহৃত; Seller product operations approval ও owner-scoped lookup দিয়ে সুরক্ষিত। Admin dashboard-এ seller/product review এবং Rider/Admin invitation controls আছে। `/auth/portal` পুরোনো dashboard route compatibility-র জন্য রয়ে গেছে।

**Acceptance review (2026-10-01)**

Focused Phase 1/2 regression set-এ প্রতিটি role-এর dashboard redirect, cross-role denial, seller-owned product access, seller review/invitation authorization এবং locale preference পাস করেছে। পুরো repository suite এখন সবুজ (58 passed)। পূর্বে চিহ্নিত তিনটি order/cart failure — cart empty-state-এর পুরোনো expected copy এবং missing order email templates (order_pending, order_receipt, order_status, admin_order) — সংশোধন করা হয়েছে।

Customer profile follow-up (2026-10-01): পুরোনো customer account-এ profile row না থাকলে account ও dashboard visit-এ row repair হয়; profile name/image dashboard-এ দেখানো হয়। এর regression coverage `test_customer_dashboard_and_account_repair_a_missing_profile_row`-এ আছে।

### Phase 3 — Multilingual catalog, Seller management ও media

**Deliverables**

- Store onboarding/approval, food/grocery/retail category, product/menu, variant, stock ও Admin moderation।
- Seller চাইলে English, বাংলা, हिन्दी ও Arabic-এ title/description পূরণ করবে; একটি ভাষায় publish করা যাবে।
- Translation lookup locale অনুযায়ী হবে; missing translation original language label-সহ দেখাবে।
- Upload quarantine, private scan, validation ও approved external storage flow।

**Acceptance gate**

- Seller approval, catalog CRUD, variants, stock, moderation ও seller isolation কাজ করে।
- অনুবাদ ও original-language fallback সঠিক; automatic machine translation নেই।
- Malicious/invalid upload quarantine-এ থাকে এবং validation pass না করা পর্যন্ত normal storage-এ যায় না।

**Repository implementation review (2026-10-01)**

Seller category/product CRUD, seller-only ownership checks, product translation lookup/search and original-language fallback, variants and stock, and Admin product moderation are implemented. Catalog image intake uses private quarantine, ClamAV CLI, Pillow decode/re-encode, and S3-compatible storage; rejected uploads stay quarantined. Focused auth/catalog/media regression checks pass: **40 passed**. Image pipeline checks mock the scanner and object store, so this confirms fail-closed behavior and processing order, not live-provider connectivity. The current workstation has no ClamAV executable or catalog media bucket/CDN configuration. Consequently the code is ready, but real image publishing and the live acceptance smoke check remain pending those deployment settings. Phase 3 code, translations, and regression coverage are complete: the full repository suite is green (58 passed).

### Phase 4 — Multi-vendor checkout, invoice ও email

**Deliverables**

- Customer-এর single cart; checkout-এ seller অনুযায়ী sub-order ও seller-specific invoice।
- প্রথম payment method Cash on Delivery (COD)।
- Buyer receipt এবং ReportLab PDF seller-specific invoice: customer locale, product translation থাকলে সেটি, না থাকলে original ও তার ভাষা, amount BDT-তে, date/number locale অনুযায়ী।
- SMTP transactional email/notification customer-এর নির্বাচিত ভাষায়; retry handling-সহ background delivery।

**Acceptance gate**

- Cart grouping, এক checkout থেকে sub-order তৈরি এবং COD flow সঠিক।
- প্রতিটি seller-এর invoice-এ সঠিক sub-order ও localized text/format থাকে।
- Email delivery failure retry হয়; diagnostic log-এ secret বা credential থাকে না।

### Phase 5 — Rider operations ও delivery state

**Deliverables**

- Order flow: creation → Admin assignment → Rider pickup → out for delivery → delivered → proof of delivery।
- Rider dashboard delivery workflow-এর জন্য optimize করা।
- প্রথম release-এ live GPS বা map থাকবে না; future location support-এর জন্য data shape প্রস্তুত রাখা যেতে পারে।

**Acceptance gate**

- Assignment, Rider access, pickup/delivery state ও proof of delivery কাজ করে।
- Unauthorized user state পরিবর্তন করতে পারে না; invalid transition প্রত্যাখ্যাত হয়।

### Phase 6 — Production security, database ও launch review

**Deliverables**

- Login throttling, Admin MFA, audit log, dependency review, backup/restore validation ও DB monitoring।
- Cloudflare WAF/Tunnel → Render private app ingress target যাচাই ও configure করা; direct public access policy deployment feasibility অনুযায়ী স্থির করা।
- 400 MB database ceiling, external file storage, locale persistence, Arabic RTL, upload quarantine, invoice/email retry-সহ production QA।

**Acceptance gate**

- Production secrets source code-এ নেই; WAF/ingress, throttling, MFA ও audit behavior review পাস করে।
- Database 400 MB-এর নিচে; backup থেকে restore যাচাই হয়েছে।
- Four-locale UI, RTL, role/data isolation, malicious upload handling ও commerce/delivery end-to-end acceptance পাস।
- Production launch review সম্পন্ন।

## ৪. সামগ্রিক পরীক্ষা ও চূড়ান্ত acceptance

প্রতিটি phase-এর gate আলাদাভাবে পরীক্ষা ও review হবে। Test coverage-এ অন্তর্ভুক্ত:

- Auth: login/sign-up/logout, CSRF, validation, session, safe redirect, throttling।
- Authorization: role redirect, unauthorized access, privilege escalation attempt, seller data isolation।
- Localization: চার locale, account/session/browser priority, en_US fallback, RTL ও translation fallback।
- Commerce: cart, seller grouping, sub-order, COD, invoice localization, email retry।
- Operations: Seller approval/moderation, Rider assignment, delivery transitions ও proof of delivery।
- Security/operations: upload quarantine, MFA, audit event, secret-safe logging, backup/restore ও DB-size limit।
- UI: responsive widths, keyboard navigation, field errors, loading/error/success এবং reduced motion।

পরিকল্পনাটি production review-এর জন্য সম্পূর্ণ ধরা হবে যখন ছয়টি phase-এর acceptance gate পাস, language preference persistence যাচাই, database 400 MB সীমার মধ্যে, এবং production ingress/backup/security review সম্পন্ন।

## ৫. খোলা সিদ্ধান্ত ও source mapping

### খোলা সিদ্ধান্ত

| বিষয় | উৎসে কী নির্ধারিত | পরবর্তী ধাপ |
|---|---|---|
| Background job | Threaded processing অথবা Celery/Redis—দুটিই বিকল্প হিসেবে আছে | Phase 4-এর আগে retry/durability ও hosting requirement দেখে পদ্ধতি স্থির |
| Upload scanning/storage | Private antivirus ও quarantine আবশ্যক; নির্দিষ্ট product/provider নেই | Code path ClamAV CLI ও S3-compatible storage দিয়ে wired; deployment-এ ClamAV executable, bucket/CDN ও credentials configure করে live smoke check করতে হবে |
| Production ingress | Cloudflare WAF/Tunnel ও Render private networking প্রস্তাবিত; WAF rule tier-dependent | Phase 6-এর আগে connector placement, private reachability ও Cloudflare tier যাচাই |
| Database capacity | Local SQLite, deployment PostgreSQL `DATABASE_URL`, PostgreSQL/Supabase proposal ও 400 MB ceiling | Provisioning-এর আগে provider, বাস্তব quota, backup, restore ও monitoring behavior নিশ্চিত |
| Auth implementation status | README integrated বললেও Phase 1 শুরুর সময় চারটি app path অনুপস্থিত ছিল | Phase 1-এ প্রয়োজনীয় auth UI ও email template যোগ হয়েছে; পরবর্তী repository review-তে README-এর path তালিকা যাচাই |

### একত্র করা উৎস

এই merged plan-এ তিনটি project plan-এর non-duplicate requirements, architecture, database proposals, six phase gates, acceptance notes ও next-stage status একত্র করা হয়েছে:

| Merged input | অন্তর্ভুক্ত বিষয় |
|---|---|
| Existing `nexhaat-master-plan.md` | Architecture, phase gates ও repository acceptance notes; এটিই merged plan হিসেবে রাখা হয়েছে |
| `PLAN.md` (merged input; removed) | Locale/default behavior, COD, buyer receipt, data constraints, conditional ingress ও launch acceptance |
| `PLANE 1.md` (merged input; removed) | Database schema proposals, role/auth architecture, media flow, detailed phase gates ও testing strategy |
| `docs/design-references/index.html`, `style.css`, `script.js`, `README.md`, `README 1.md` | Archived auth design reference ও accessibility/security constraints |

Merge-এর পর `PLAN.md` এবং `PLANE 1.md` source copy মুছে ফেলা হয়েছে; নামগুলো এখানে শুধু provenance হিসেবে রাখা হয়েছে।
