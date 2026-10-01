(() => {
  "use strict";

  const card = document.querySelector("[data-auth-card]");
  const authModes = ["login", "signup", "seller"];

  function setMode(mode, focusHeading = false) {
    if (!card || !authModes.includes(mode)) return;
    card.dataset.mode = mode;
    card.querySelectorAll("[data-auth-panel]").forEach((panel) => {
      const active = panel.dataset.authPanel === mode;
      panel.inert = !active;
      panel.setAttribute("aria-hidden", String(!active));
    });
    if (focusHeading) {
      card.querySelector('[data-auth-panel="' + mode + '"] h1')?.focus({ preventScroll: true });
    }
  }

  if (card) {
    setMode(card.dataset.mode || "login");
    card.addEventListener("click", (event) => {
      const link = event.target.closest("[data-auth-switch]");
      if (!link) return;
      event.preventDefault();
      const mode = link.dataset.authSwitch;
      setMode(mode, true);
      window.history.pushState({ authMode: mode }, "", link.href);
    });
    window.addEventListener("popstate", () => {
      const path = window.location.pathname.replace(/\/$/, "");
      const mode = path.endsWith("/register")
        ? "signup"
        : path.endsWith("/seller-application")
          ? "seller"
          : "login";
      setMode(mode);
    });
  }

  // Carry a short page-turn into the separate forgot/reset auth routes.
  const authMain = document.querySelector(".auth-main");
  const routeFlipKey = "nexhaat-auth-route-flip";
  if (authMain) {
    try {
      if (window.sessionStorage.getItem(routeFlipKey) === "1") {
        window.sessionStorage.removeItem(routeFlipKey);
        authMain.classList.add("auth-page-flip-in");
        window.setTimeout(() => authMain.classList.remove("auth-page-flip-in"), 900);
      }
    } catch (_) {
      // Storage can be unavailable in private browsing; the page remains usable.
    }

    let navigating = false;
    document.addEventListener("click", (event) => {
      const link = event.target.closest?.("a[data-auth-page-flip]");
      if (!link || navigating || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target) return;
      if (link.origin !== window.location.origin || link.hasAttribute("download")) return;

      event.preventDefault();
      navigating = true;
      try {
        window.sessionStorage.setItem(routeFlipKey, "1");
      } catch (_) {
        // Continue to the destination even when storage is unavailable.
      }

      const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      const delay = reducedMotion ? 0 : 420;
      authMain.classList.add("auth-page-flip-out");
      window.setTimeout(() => window.location.assign(link.href), delay);
    });
  }

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    const input = document.getElementById(button.getAttribute("aria-controls"));
    if (!input) return;
    button.hidden = false;
    button.addEventListener("click", () => {
      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      button.setAttribute("aria-pressed", String(reveal));
      button.setAttribute("aria-label", reveal ? button.dataset.hideLabel : button.dataset.showLabel);
    });
  });

  document.querySelectorAll("[data-profile-image-input]").forEach((input) => {
    const avatar = document.getElementById(input.dataset.previewTarget || "");
    if (!avatar) return;

    const originalImage = avatar.querySelector("img");
    const originalSource = originalImage?.getAttribute("src") || "";
    const originalAlt = originalImage?.alt || input.dataset.previewAlt || "";
    let previewUrl = "";

    function showInitial() {
      const initial = document.createElement("span");
      initial.dataset.avatarInitial = "";
      initial.setAttribute("aria-hidden", "true");
      initial.textContent = avatar.dataset.initial || "?";
      avatar.replaceChildren(initial);
    }

    function showImage(source, alt) {
      const image = document.createElement("img");
      image.dataset.profileAvatarImage = "";
      image.alt = alt;
      image.addEventListener("error", showInitial, { once: true });
      image.src = source;
      avatar.replaceChildren(image);
    }

    if (originalSource) {
      originalImage.addEventListener("error", showInitial, { once: true });
    }

    input.addEventListener("change", () => {
      if (previewUrl) window.URL.revokeObjectURL(previewUrl);
      previewUrl = "";

      const file = input.files?.[0];
      if (!file) {
        if (originalSource) showImage(originalSource, originalAlt);
        else showInitial();
        return;
      }
      if (!file.type.startsWith("image/")) return;

      try {
        previewUrl = window.URL.createObjectURL(file);
        showImage(previewUrl, input.dataset.previewAlt || originalAlt);
      } catch (_) {
        showInitial();
      }
    });
  });

  function updatePasswordMatch(field) {
    const sourceId = field.dataset.confirmFor;
    if (!sourceId) return;
    const source = document.getElementById(sourceId);
    if (source && field.value && field.value !== source.value) {
      field.setCustomValidity(field.dataset.mismatchMessage || "");
    } else {
      field.setCustomValidity("");
    }
  }

  function fieldMessage(field) {
    const validity = field.validity;
    if (validity.valueMissing) return field.dataset.requiredMessage || field.validationMessage;
    if (validity.typeMismatch && field.type === "email") {
      return field.dataset.emailMessage || field.validationMessage;
    }
    if (validity.tooShort && field.dataset.tooShortMessage) return field.dataset.tooShortMessage;
    if (validity.tooLong && field.dataset.tooLongMessage) return field.dataset.tooLongMessage;
    if (validity.customError && field.dataset.mismatchMessage) return field.dataset.mismatchMessage;
    return field.validationMessage;
  }

  function showFieldState(field, revealError) {
    const error = field.id
      ? document.getElementById(field.id + "-error")
      : field.closest(".form-field")?.querySelector("[data-field-error]");
    const invalid = !field.validity.valid;
    field.setAttribute("aria-invalid", String(invalid));
    if (error) error.textContent = invalid && revealError ? fieldMessage(field) : "";
    return !invalid;
  }

  document.querySelectorAll("[data-validate-form]").forEach((form) => {
    const fields = Array.from(form.querySelectorAll("[data-validate]"));
    form.noValidate = true;
    fields.forEach((field) => {
      field.addEventListener("input", () => {
        updatePasswordMatch(field);
        if (field.dataset.touched === "true") showFieldState(field, true);
        fields
          .filter((candidate) => candidate.dataset.confirmFor === field.id)
          .forEach((confirmation) => {
            updatePasswordMatch(confirmation);
            if (confirmation.dataset.touched === "true") showFieldState(confirmation, true);
          });
      });
      field.addEventListener("blur", () => {
        updatePasswordMatch(field);
        field.dataset.touched = "true";
        showFieldState(field, true);
        fields
          .filter((candidate) => candidate.dataset.confirmFor === field.id)
          .forEach((confirmation) => {
            updatePasswordMatch(confirmation);
            if (confirmation.dataset.touched === "true") showFieldState(confirmation, true);
          });
      });
    });

    form.addEventListener("submit", (event) => {
      fields.forEach(updatePasswordMatch);
      let firstInvalid = null;
      fields.forEach((field) => {
        field.dataset.touched = "true";
        if (!showFieldState(field, true) && !firstInvalid) firstInvalid = field;
      });
      if (firstInvalid) {
        event.preventDefault();
        firstInvalid.focus();
        return;
      }

      const button = form.querySelector('button[type="submit"][data-loading-label]');
      if (button) {
        button.setAttribute("aria-busy", "true");
        button.disabled = true;
        const label = button.querySelector("[data-submit-label]");
        if (label) label.textContent = button.dataset.loadingLabel;
      }
    });
  });
})();
