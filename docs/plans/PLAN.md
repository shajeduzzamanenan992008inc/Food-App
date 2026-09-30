# NexHaat: সম্পূর্ণ প্রকল্পের ৬ ধাপ ও multilingual support

## সারাংশ

NexHaat হবে Customer, Seller, Rider ও Admin—এই চার পোর্টালের একটি marketplace। বাস্তবায়ন ধাপে ধাপে হবে; প্রতিটি ধাপ review ও acceptance শেষ হলে পরের ধাপ শুরু হবে।

সাইটে শুরু থেকেই চারটি ভাষা থাকবে: **English (US) default**, বাংলা, हिन्दी এবং العربية। ভাষা বদলালে UI, form validation, notification ও transactional email সেই ভাষায় দেখাবে। Arabic-এর জন্য RTL layout থাকবে। Seller-এর পণ্য এক ভাষায় publish করা যাবে; অন্য ভাষার অনুবাদ দিলে সেটি দেখাবে, না দিলে original text-এর সঙ্গে তার ভাষা চিহ্নিত থাকবে।

## ৬টি ধাপ

1. **Login/Sign Up, brand ও language foundation:** `Login & Sign Up Form`-এর HTML/CSS/JS-কে Flask/Jinja auth page ও static asset-এ সরিয়ে integrate করা; neumorphic design, flip animation, responsive ও accessible form তৈরি। NexHaat branding ও favicon যোগ হবে। Flask-Babel, gettext translation catalog এবং language selector বসিয়ে `en_US`, `bn_BD`, `hi_IN`, `ar` চালু হবে। [Flask-Babel documentation](https://python-babel.github.io/flask-babel/)
2. **চার role ও dashboard:** এক Login-এ database role অনুযায়ী dashboard redirect; Customer সরাসরি signup, Seller আবেদন ও Admin approval, Rider/Admin account Admin তৈরি বা invite করবে। প্রতিটি role-এর permission ও language preference থাকবে।
3. **Seller/Admin catalog:** Store onboarding, Seller approval, food/grocery/retail category, product/menu, variant, stock ও Admin moderation। Seller ঐচ্ছিকভাবে চার ভাষায় title/description দেবে; অনুবাদ না থাকলে original দেখাবে।
4. **Customer checkout, invoice ও email:** এক cart/checkout থেকে Seller-ভিত্তিক sub-order, প্রথমে COD, buyer receipt ও seller-specific invoice। Email ও invoice-এর ভাষা গ্রাহকের নির্বাচিত locale অনুযায়ী হবে; amount BDT-তে থাকবে, তারিখ/সংখ্যা locale অনুযায়ী format হবে।
5. **Rider ও delivery operations:** Admin assignment, Rider-এর pickup/delivery status এবং proof of delivery; প্রথম সংস্করণে live GPS/map থাকবে না।
6. **Security, database ও launch:** Firewall/WAF, private antivirus scanning ও quarantine, dependency checks, backup/restore, multilingual QA এবং production launch review।

## Interfaces, security ও data constraints

- Language selector-এর জন্য CSRF-protected `POST /language` route থাকবে। Signed-in user-এর পছন্দ account-এ সংরক্ষিত হবে; anonymous user-এর পছন্দ session-এ থাকবে। অগ্রাধিকার: saved account preference → explicit session selection → browser language → `en_US` fallback।
- Translation catalog থেকে interface/system text অনূদিত হবে। Seller-provided content স্বয়ংক্রিয়ভাবে machine translate হবে না; invoice generation-এর সময় নির্বাচিত ভাষার product text থাকলে তা ব্যবহার হবে, নইলে original language label-সহ original text থাকবে।
- Database সর্বোচ্চ **400 MB**; image/file বাইরে থাকবে। যাচাইযোগ্য real food/category record রাখা হবে—এই সীমায় ১ বিলিয়ন real food row সম্ভব নয়, duplicate data তৈরি করে সংখ্যাটি পূরণ করা হবে না।
- Admin MFA, login throttling, audit log, role ও Seller-ভিত্তিক data isolation এবং upload quarantine থাকবে। Cloudflare WAF → Tunnel → private Render app হবে প্রস্তাবিত ingress; এটি Render private networking ও Cloudflare Tunnel-এর documented capability থেকে নেওয়া architecture inference। [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/), [Render private services](https://render.com/docs/private-services), [Render private network](https://render.com/docs/private-network/). WAF rule account tier অনুযায়ী হবে। [Cloudflare managed rules](https://developers.cloudflare.com/waf/managed-rules/)

## Acceptance ও assumptions

প্রতি ধাপে সংশ্লিষ্ট feature পরীক্ষা হবে। চূড়ান্ত acceptance-এ থাকবে: Login/Sign Up ও CSRF, role redirect ও data isolation, Seller approval, multi-seller checkout, সঠিক invoice/email retry, Rider status flow, malicious upload quarantine, database 400 MB-এর নিচে, এবং চার ভাষায় সম্পূর্ণ UI—বিশেষ করে Arabic RTL ও language preference persistence। Layered defense লক্ষ্য হবে; কোনো ব্যবস্থা শতভাগ hack-proof হওয়ার নিশ্চয়তা দেয় না।
