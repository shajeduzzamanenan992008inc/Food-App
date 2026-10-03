(() => {
  "use strict";

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
  const favicon = document.querySelector('link[rel="icon"][data-static-href]');
  if (favicon) {
    const animatedHref = favicon.href;
    const applyFaviconMotion = () => {
      const reduced = reducedMotion.matches;
      favicon.type = reduced ? "image/svg+xml" : "image/gif";
      favicon.href = reduced ? favicon.dataset.staticHref : animatedHref;
    };
    applyFaviconMotion();
    reducedMotion.addEventListener?.("change", applyFaviconMotion);
  }

  const syncFloatingField = (field, control) => {
    const hasValue = control.type === "date" || control.type === "datetime-local"
      ? Boolean(control.value)
      : Boolean(control.value && control.value.trim());
    field.classList.toggle("has-value", hasValue);
  };

  document.querySelectorAll(".form-field").forEach((field) => {
    const candidates = field.querySelectorAll(
      'input:not([type="checkbox"]):not([type="radio"]):not([type="file"]):not([type="hidden"]), textarea'
    );
    const labels = field.querySelectorAll(":scope > label");
    const label = labels[0];
    if (candidates.length !== 1 || labels.length !== 1 || !label || label.hidden || label.hasAttribute("aria-hidden") || label.classList.contains("visually-hidden")) return;

    const control = candidates[0];
    field.classList.add("form-field--floating");
    if (!control.hasAttribute("placeholder") && (control.tagName === "TEXTAREA" || ["text", "email", "password", "tel", "search", "url", "number"].includes(control.type))) {
      control.setAttribute("placeholder", " ");
    }
    syncFloatingField(field, control);
    control.addEventListener("input", () => syncFloatingField(field, control));
    control.addEventListener("change", () => syncFloatingField(field, control));
    control.addEventListener("focus", () => field.classList.add("is-active"));
    control.addEventListener("blur", () => {
      field.classList.remove("is-active");
      syncFloatingField(field, control);
    });
    [160, 480, 1000].forEach((delay) => window.setTimeout(() => syncFloatingField(field, control), delay));
  });

  // Fill an optional slug field from its source field while the user has not typed one.
  document.querySelectorAll("[data-slug-source]").forEach((source) => {
    const target = document.getElementById(source.dataset.slugSource);
    if (!target) return;
    let touched = Boolean(target.value);
    target.addEventListener("input", () => { touched = true; });
    const sync = () => {
      if (touched) return;
      target.value = source.value
        .normalize("NFKD")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 180);
    };
    source.addEventListener("input", sync);
    source.addEventListener("blur", sync);
    sync();
  });

  if (!reducedMotion.matches && finePointer.matches) {
    document.querySelectorAll(".product-card, .category-tile, .stat-card, .workspace-card").forEach((card) => {
      card.setAttribute("data-3d-tilt", "true");
      card.addEventListener("pointermove", (event) => {
        if (event.pointerType !== "mouse") return;
        const bounds = card.getBoundingClientRect();
        const x = (event.clientX - bounds.left) / bounds.width - 0.5;
        const y = (event.clientY - bounds.top) / bounds.height - 0.5;
        card.style.setProperty("--tilt-x", `${(x * 5).toFixed(2)}deg`);
        card.style.setProperty("--tilt-y", `${(y * -4).toFixed(2)}deg`);
      });
      card.addEventListener("pointerleave", () => {
        card.style.removeProperty("--tilt-x");
        card.style.removeProperty("--tilt-y");
      });
    });
  }

  const navToggle = document.querySelector(".nav-toggle");
  if (navToggle) {
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && navToggle.checked) {
        navToggle.checked = false;
        navToggle.focus();
      }
    });
    document.querySelectorAll(".site-nav a").forEach((link) => {
      link.addEventListener("click", () => { navToggle.checked = false; });
    });
  }
})();
