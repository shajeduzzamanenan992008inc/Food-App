# NexHaat — ULTRA UPGRADE MASTER PLAN

## 0. Project Vision

NexHaat হবে একটি modular multilingual marketplace যেখানে চারটি role থাকবে:

* Customer
* Seller
* Rider
* Admin

প্রতিটি phase আলাদাভাবে implement, test, review এবং acceptance-এর পরেই পরবর্তী phase শুরু হবে।

শুরু থেকেই supported language:

* English (US) — Default
* বাংলা
* हिन्दी
* العربية

ভাষা পরিবর্তনের প্রভাব UI, form validation, notification এবং transactional email-এ প্রযোজ্য হবে। Arabic-এর জন্য সম্পূর্ণ RTL layout থাকবে।

---

# 1. ULTRA Architecture

## Application Layer

```text
Cloudflare WAF
      ↓
Cloudflare Tunnel / Zero Trust
      ↓
Render Web Service
      ↓
Flask Application
      ↓
Blueprint / RBAC Layer
      ↓
Service Layer
      ↓
PostgreSQL / Supabase
```

Core stack:

* Python
* Flask
* Flask-Login
* Flask-Babel
* Flask-Blueprint
* PostgreSQL / Supabase
* JSONB multilingual fields
* Render
* Docker
* External file storage

Cloudflare WAF, Tunnel এবং Render private networking security architecture-এর অংশ হিসেবে থাকবে।

---

# 2. Database Strategy

Database সর্বোচ্চ **400 MB** সীমার মধ্যে থাকবে। Image এবং file database-এর বাইরে রাখা হবে।

## users

```text
id
role
email
password_hash
locale_preference
2fa_enabled
```

Role:

```text
admin
seller
rider
customer
```

## products

```text
id
seller_id
category_id
price_bdt
stock
status
title_translations JSONB
desc_translations JSONB
```

Example:

```json
{
  "en": "Apple",
  "bn": "আপেল",
  "hi": "सेब",
  "ar": "تُفَّاح"
}
```

User locale অনুযায়ী translation ব্যবহার হবে।

Translation না থাকলে original text দেখানো হবে এবং original language label দেখানো হবে।

---

# 3. Language Resolution Engine

Language priority হবে:

```text
Saved Account Preference
        ↓
Explicit Session Selection
        ↓
Browser Language
        ↓
en_US
```

Signed-in user-এর language account-এ সংরক্ষিত হবে, anonymous user's selection session-এ থাকবে। `/language` route CSRF-protected হবে।

Supported locale:

```text
en_US
bn_BD
hi_IN
ar
```

---

# 4. Ultra Authentication Foundation

## Auth UI

Login এবং Sign Up interface হবে:

* Neumorphic
* 3D-inspired
* Responsive
* Accessible
* Animated
* Multilingual

Live Flask/Jinja implementation:

```text
app/templates/auth/_auth_card.html
app/templates/auth/base.html

app/static/css/auth.css
app/static/js/auth.js
```

Original HTML/CSS/JS design reference হিসেবে archive থাকবে; live application সরাসরি archived files serve করবে না.

## Authentication Security

* CSRF protection
* Secure password hashing
* Session security
* Server-side validation
* Login throttling
* Admin MFA
* Audit logging

---

# 5. Role & Authorization Architecture

চারটি আলাদা role-based Blueprint:

```text
/admin
/seller
/rider
/customer
```

Custom authorization decorators ব্যবহার করা হবে।

Example:

```python
@seller_required
```

Login-এর পরে database role অনুযায়ী dashboard redirect হবে।

Authorization শুধু frontend visibility-এর ওপর নির্ভর করবে না; server-side permission এবং data isolation enforce হবে।

---

# 6. Six-Phase Ultra Execution

## PHASE 1

### Foundation + Security + i18n Core

### Deliverables

Auth foundation:

* Flask-Login
* Login
* Sign Up
* CSRF
* Server validation
* Neumorphic UI
* Flip animation
* Responsive layout
* Accessibility

Language foundation:

* Flask-Babel
* Translation catalog
* Language selector
* `POST /language`
* Session preference
* Account preference
* Browser fallback
* `en_US` fallback

Arabic:

* RTL
* CSS Logical Properties
* Direction-aware layout

### Phase Gate

Phase 1 accepted only when:

```text
Login works
Sign Up works
CSRF works
Validation works
4 languages work
Language persistence works
Arabic RTL works
Responsive UI works
```

---

# PHASE 2

### Role-Based Dashboards + Access Control

Create:

```text
Admin Dashboard
Seller Dashboard
Rider Dashboard
Customer Dashboard
```

Implement:

* Four Blueprints
* RBAC decorators
* Role-aware routing
* Permission checks
* Data isolation
* Admin-controlled Rider/Admin account creation or invitation
* Seller application and Admin approval

Customer can sign up directly.

Seller requires approval.

Rider/Admin account creation remains Admin-controlled.

### Phase Gate

Verify:

```text
Correct role → correct dashboard
Wrong role → denied
Seller data isolation works
Customer cannot access Admin
Rider cannot access Seller/Admin
Admin controls privileged operations
```

---

# PHASE 3

### Multilingual Catalog + Seller Management

Seller functionality:

* Store onboarding
* Seller approval
* Category management
* Product/menu management
* Variant
* Stock
* Admin moderation

Translation fields:

```text
English
বাংলা
हिन्दी
العربية
```

Seller may publish with one language.

Additional translations are optional.

Missing translations must show original content with language identification. Automatic machine translation of seller-provided content is not part of the design.

## Media Security

Uploads:

```text
Upload
  ↓
Quarantine
  ↓
Private antivirus scan
  ↓
Validation
  ↓
Approved storage
```

Malicious files must never enter normal application storage before validation.

### Phase Gate

```text
Seller approval works
Catalog works
Translation works
Original fallback works
Variant works
Stock works
Upload quarantine works
Admin moderation works
```

---

# PHASE 4

### Multi-Vendor Checkout + Invoice + Async Email

## Cart

Customer maintains one cart.

At checkout:

```text
Customer Cart
      ↓
Seller grouping
      ↓
Sub-orders
      ↓
Seller-specific invoice
```

Initial payment method:

```text
COD
```

## Invoice

Generate PDF with ReportLab.

Invoice:

* Uses customer's selected locale
* Uses seller/product translation when available
* Falls back to original language when necessary
* Amount remains BDT
* Date/number formatting follows locale

## Email

Use:

* SMTP
* Threaded/background processing or Celery/Redis
* Retry handling

Notifications and transactional email use the selected customer language.

### Phase Gate

```text
Cart works
Seller grouping works
Sub-orders work
COD works
Invoice works
Locale formatting works
Email works
Email retry works
```

---

# PHASE 5

### Rider Operations + Delivery State Machine

Order lifecycle:

```text
Order Created
      ↓
Admin Assignment
      ↓
Rider Pickup
      ↓
Out for Delivery
      ↓
Delivered
      ↓
Proof of Delivery
```

Rider dashboard will be optimized for delivery workflows.

First version:

```text
NO live GPS
NO live map
```

Database structure may remain future-ready for later location functionality.

### Phase Gate

```text
Assignment works
Rider access works
Pickup state works
Delivery state works
Proof of delivery works
Unauthorized state changes blocked
```

---

# PHASE 6

### Enterprise Security + Database Optimization + Launch

## Security

Final production architecture:

```text
Cloudflare WAF
      ↓
Cloudflare Tunnel
      ↓
Private Render Application
```

Apply:

* WAF managed rules
* Login throttling
* Admin MFA
* Audit logs
* Role isolation
* Seller isolation
* Upload quarantine
* Dependency checks

The WAF rule set depends on the applicable Cloudflare account tier.

## Database

Keep database below:

```text
400 MB
```

Rules:

* No artificial duplicate data
* No fake billion-row target
* Real, verifiable food/category data
* External storage for large files
* Database monitoring
* Backup/restore validation

---

# 7. Ultra Testing Strategy

Every phase receives its own QA before acceptance.

## Authentication

```text
Login
Sign Up
Logout
CSRF
Validation
Session
Role redirect
```

## Authorization

```text
Role isolation
Seller isolation
Unauthorized route access
Privilege escalation attempts
```

## Localization

```text
English
বাংলা
हिन्दी
العربية
RTL
Persistence
Fallback
```

## Commerce

```text
Cart
Multi-vendor grouping
COD
Sub-order
Invoice
Email
Retry
```

## Operations

```text
Seller approval
Admin moderation
Rider assignment
Delivery states
Proof of delivery
```

## Security

```text
Upload quarantine
MFA
Throttling
Audit log
Dependency checks
```

---

# 8. Final Acceptance Gate

The project is ready for production review only when all of the following are verified:

```text
[✓] Login / Sign Up
[✓] CSRF
[✓] Role redirect
[✓] RBAC
[✓] Data isolation
[✓] Seller approval
[✓] Catalog
[✓] Multilingual product data
[✓] Original-language fallback
[✓] Multi-vendor cart
[✓] Seller-specific sub-orders
[✓] COD
[✓] PDF Invoice
[✓] Localized Invoice
[✓] SMTP Email
[✓] Email Retry
[✓] Rider workflow
[✓] Delivery state machine
[✓] Proof of delivery
[✓] Upload quarantine
[✓] Admin MFA
[✓] Audit log
[✓] Database < 400 MB
[✓] English
[✓] বাংলা
[✓] हिन्दी
[✓] العربية
[✓] Arabic RTL
[✓] Language persistence
[✓] Production QA
```

---

# 9. Non-Negotiable Architecture Rules

### Rule 1

এক phase-এর কাজ acceptance ছাড়া পরের phase-এ যাবে না।

### Rule 2

Frontend কখনো authorization-এর একমাত্র নিরাপত্তা layer হবে না।

### Rule 3

Seller content automatic machine translation করা হবে না।

### Rule 4

Database limit পূরণ করার জন্য duplicate/fake data তৈরি করা হবে না।

### Rule 5

Image/file database-এর মধ্যে unnecessarily রাখা হবে না।

### Rule 6

Production secrets source code বা Git repository-তে রাখা হবে না।

### Rule 7

Architecture modular থাকবে; একটি feature-এর জন্য অপ্রয়োজনীয় নতুন system যোগ করা হবে না।

### Rule 8

কোনো security layer-কে 100% hack-proof হিসেবে ধরা হবে না; layered defense ব্যবহার করা হবে।

---

# 10. Final NexHaat Architecture

```text
                     NEXHAAT
                        │
             ┌──────────┴──────────┐
             │                     │
        Multilingual           Security
         UI / i18n              Layer
             │                     │
             └──────────┬──────────┘
                        │
                 Flask Application
                        │
        ┌───────────────┼───────────────┐
        │               │               │
      Admin           Seller          Customer
        │               │               │
        └───────────────┼───────────────┘
                        │
                      Rider
                        │
                 Service Layer
                        │
                PostgreSQL/Supabase
                        │
               External File Storage
```

## End State

NexHaat-এর লক্ষ্য হবে একটি:

**Multilingual + Multi-Role + Secure + Modular + Accessible + Production-Oriented Marketplace**

যার core delivery ৬টি controlled phase-এর মাধ্যমে সম্পন্ন হবে এবং প্রতিটি phase আলাদা acceptance gate পাস করবে।
