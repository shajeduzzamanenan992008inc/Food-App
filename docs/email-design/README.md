# NexHaat 3D Neumorphic Email System

This directory contains standalone, 3D Neumorphic transactional email templates and an interactive studio based directly on the design references in [`docs/design-references/`](../design-references/).

---

## 🎨 3D Design & Animation Engine

1. **Neumorphic Canvas & Card:**
   - Background: `#e7ebf0`
   - Double Outset Shadow: `box-shadow: 20px 20px 40px rgba(163, 177, 198, .65), -20px -20px 40px rgba(255, 255, 255, .95)`
   - Double Inset Shadow: `box-shadow: inset 6px 6px 12px rgba(163, 177, 198, .55), inset -6px -6px 12px rgba(255, 255, 255, .95)`
   - Corner Radius: `35px` for primary panels, `18px-20px` for embedded displays.

2. **Electric Rotating Conic-Gradient Glow:**
   - Rotating border running `@keyframes electricRotate` with a conic blend of `#00eaff`, `#00aaff`, and `#006cff`.
   - Subtle outer glow blur filter (`filter: blur(8px)`).

3. **3D Card Flip (`.auth-card.flipped`):**
   - 3D space (`perspective: 1600px`, `transform-style: preserve-3d`)
   - Rotates 180 degrees to switch between interactive visual email view and production HTML code view.

4. **Liquid Wave Gradient Hover Buttons:**
   - `.main-btn` features an animated sliding liquid gradient on hover (`linear-gradient(110deg, #006cff, #00cfff, #006cff)`) running `@keyframes buttonMove`.

---

## 📁 Files Included

- **[`index.html`](./index.html)** — Interactive 3D Neumorphic Studio & Email Previewer. Includes 3D card flip, template switcher, electric glow animation, and one-click clean code export.
- **[`otp-verification.html`](./otp-verification.html)** — 3D Neumorphic OTP Access Code verification email.
- **[`order-receipt.html`](./order-receipt.html)** — 3D Neumorphic Order Confirmation & Receipt email with itemized table and electric grand total highlight.
- **[`order-status.html`](./order-status.html)** — 3D Neumorphic Delivery Status email with 4-stage tracking stepper.
- **[`account-invitation.html`](./account-invitation.html)** — 3D Neumorphic Staff / Partner Onboarding email.
- **[`reference.html`](./reference.html)** — Master baseline reference email template.

---

## 🖥️ How to Preview

To view the interactive 3D studio:
```powershell
Start-Process "docs\email-design\index.html"
```
