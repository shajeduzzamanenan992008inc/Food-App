(() => {
  "use strict";

  const ORBIT_DURATION = 1600;
  const ORBIT_PAUSE = 180;
  const LOADING_DURATION = 2000;

  const form = document.querySelector("[data-otp-form]");
  const card = document.getElementById("otp-card");
  if (!form || !card) return;

  const digits = Array.from(form.querySelectorAll("[data-otp-digit]"));
  const inputStage = form.querySelector("[data-otp-input-stage]");
  const fallback = document.getElementById("otp-fallback");
  const title = form.querySelector("[data-otp-title]");
  const subtitle = form.querySelector("[data-otp-subtitle]");
  const error = form.querySelector("[data-otp-error]");
  const submitButton = form.querySelector("[data-otp-submit]");
  const orbitLayer = form.querySelector("[data-otp-orbit]");
  const orbitRing = form.querySelector("[data-otp-orbit-ring]");
  const loadingWrap = form.querySelector("[data-otp-loading]");
  const progress = form.querySelector("[data-otp-progress]");
  const successWrap = form.querySelector("[data-otp-success]");
  let errorResult = form.querySelector("[data-otp-error-result]");
  if (!errorResult) {
    errorResult = document.createElement("div");
    errorResult.className = "error-result";
    errorResult.dataset.otpErrorResult = "";
    errorResult.setAttribute("aria-hidden", "true");

    const flash = document.createElement("span");
    flash.className = "error-flash";
    const vault = document.createElement("span");
    vault.className = "error-vault";
    const mark = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    mark.setAttribute("viewBox", "0 0 24 24");
    mark.setAttribute("class", "error-mark");
    mark.setAttribute("aria-hidden", "true");
    const cross = document.createElementNS("http://www.w3.org/2000/svg", "path");
    cross.setAttribute("d", "M6 6l12 12M18 6L6 18");
    mark.appendChild(cross);
    vault.appendChild(mark);
    const badge = document.createElement("span");
    badge.className = "error-badge";
    badge.textContent = form.dataset.errorTitle;
    errorResult.append(flash, vault, badge);
    inputStage.parentElement.appendChild(errorResult);
  }
  const pointerLight = document.getElementById("otp-pointer-light");
  const originalTitle = title.textContent;
  const originalSubtitle = subtitle.textContent;

  let state = "idle";
  let autoSubmitTimer = null;

  document.documentElement.classList.add("otp-enhanced");
  form.noValidate = true;

  function codeValue() {
    return digits.map((input) => input.value).join("");
  }

  function syncFallback() {
    fallback.value = codeValue();
  }

  function setProgress(percent) {
    progress.textContent = String(percent) + "%";
    progress.setAttribute("aria-valuenow", String(percent));
  }

  function setLocked(locked) {
    digits.forEach((input) => { input.disabled = locked; });
    if (submitButton) submitButton.disabled = locked;
  }

  function resetSuccessAnimations() {
    successWrap.querySelectorAll(".bubble, .success-flash").forEach((element) => {
      element.style.animation = "none";
      void element.offsetWidth;
      element.style.animation = "";
    });
  }

  function clearVisuals() {
    card.dataset.state = "idle";
    card.classList.remove("shake", "success-tint", "error-tint");
    error.classList.remove("show");
    error.textContent = "";
    title.textContent = originalTitle;
    subtitle.textContent = originalSubtitle;
    setProgress(0);

    inputStage.style.display = "flex";
    inputStage.classList.remove("hidden");
    orbitLayer.classList.remove("active");
    orbitRing.classList.remove("spin");
    orbitRing.replaceChildren();
    loadingWrap.classList.remove("active");
    loadingWrap.setAttribute("aria-hidden", "true");
    successWrap.classList.remove("active");
    successWrap.setAttribute("aria-hidden", "true");
    errorResult.classList.remove("active");
    errorResult.setAttribute("aria-hidden", "true");
    successWrap.querySelectorAll(".confetti").forEach((piece) => piece.remove());
    resetSuccessAnimations();
    digits.forEach((input) => input.classList.remove("error"));
  }

  function resetState(immediateFocus) {
    window.clearTimeout(autoSubmitTimer);
    state = "idle";
    clearVisuals();
    digits.forEach((input) => {
      input.value = "";
      input.classList.remove("filled", "error");
    });
    syncFallback();
    setLocked(false);
    if (immediateFocus !== false) digits[0].focus();
  }

  function distribute(value, startAt) {
    digits.slice(startAt).forEach((input) => {
      input.value = "";
      input.classList.remove("filled", "error");
    });

    const available = digits.length - startAt;
    const chars = value.replace(/\D/g, "").slice(0, available).split("");
    chars.forEach((char, offset) => {
      const input = digits[startAt + offset];
      if (input) input.value = char;
    });

    syncFallback();
    digits.forEach((input) => input.classList.toggle("filled", Boolean(input.value)));
    const next = digits.find((input) => !input.value);
    (next || digits[digits.length - 1]).focus();
    if (!next) scheduleVerification();
  }

  function buildOrbit() {
    orbitRing.replaceChildren();
    const radius = 70;

    digits.forEach((input, index) => {
      const angle = (index / digits.length) * Math.PI * 2 - Math.PI / 2;
      const node = document.createElement("div");
      node.className = "orbit-node";
      node.textContent = input.value;
      node.style.setProperty("--dx", String(Math.cos(angle) * radius) + "px");
      node.style.setProperty("--dy", String(Math.sin(angle) * radius) + "px");
      node.style.animationDelay = String(index * 60) + "ms";
      orbitRing.appendChild(node);
    });
  }

  function vibrate(pattern) {
    if (navigator.vibrate) navigator.vibrate(pattern);
  }

  function spawnSplash() {
    const colors = ["#087cff", "#075cbd", "#3da1ff", "#80c4ff", "#16865d", "#42c994", "#e6f1ff", "#ffffff"];

    successWrap.querySelectorAll(".confetti").forEach((piece) => piece.remove());
    for (let index = 0; index < 24; index += 1) {
      const angle = (index / 24) * Math.PI * 2 + (Math.random() - 0.5) * 0.25;
      const distance = 90 + Math.random() * 70;
      const color = colors[index % colors.length];
      const piece = document.createElement("div");
      piece.className = "confetti";
      piece.style.background = color;
      piece.style.setProperty("--cx", String(Math.cos(angle) * distance) + "px");
      piece.style.setProperty("--cy", String(Math.sin(angle) * distance) + "px");
      piece.style.animationDelay = String(0.1 + Math.random() * 0.15) + "s";
      piece.style.boxShadow = "0 0 12px " + color;

      const size = 6 + Math.random() * 10;
      piece.style.width = String(size) + "px";
      piece.style.height = String(size) + "px";
      if (index % 4 === 0) piece.style.borderRadius = "2px";
      else if (index % 4 === 1) piece.style.borderRadius = "50% 0 50% 0";
      else piece.style.borderRadius = "50%";
      successWrap.appendChild(piece);
    }
  }

  function animateProgress() {
    const started = performance.now();

    function tick(now) {
      if (state !== "checking") return;
      const fraction = Math.min((now - started) / LOADING_DURATION, 1);
      const eased = 1 - Math.pow(1 - fraction, 2.2);
      setProgress(Math.round(eased * 100));
      if (fraction < 1) window.requestAnimationFrame(tick);
    }

    window.requestAnimationFrame(tick);
  }

  function showError(message, redirect) {
    state = "error";
    card.dataset.state = "error";
    card.classList.add("shake");
    card.classList.add("error-tint");
    error.textContent = message || form.dataset.errorMessage;
    error.classList.add("show");
    title.textContent = form.dataset.errorTitle;
    subtitle.textContent = form.dataset.errorSubtitle;
    inputStage.classList.add("hidden");
    inputStage.style.display = "none";
    errorResult.classList.add("active");
    errorResult.setAttribute("aria-hidden", "false");
    setLocked(true);
    digits.forEach((input) => input.classList.add("error"));
    vibrate([20, 60, 20]);
    window.setTimeout(() => card.classList.remove("shake"), 500);

    if (redirect) {
      window.setTimeout(() => window.location.assign(redirect), 1600);
      return;
    }
    window.setTimeout(() => {
      if (state !== "error") return;
      const retryMessage = message || form.dataset.errorMessage;
      resetState(false);
      error.textContent = retryMessage;
      error.classList.add("show");
      digits[0].focus();
    }, 1450);
  }

  async function verify() {
    if (state === "orbit" || state === "checking" || state === "success") return;

    window.clearTimeout(autoSubmitTimer);
    clearVisuals();
    syncFallback();

    if (!/^\d{6}$/.test(fallback.value)) {
      state = "error";
      card.dataset.state = "error";
      error.textContent = form.dataset.errorMessage;
      error.classList.add("show");
      digits.forEach((input) => input.classList.toggle("error", !input.value));
      card.classList.add("shake");
      window.setTimeout(() => card.classList.remove("shake"), 500);
      return;
    }

    state = "orbit";
    card.dataset.state = "orbit";
    setLocked(true);
    inputStage.classList.add("hidden");
    buildOrbit();
    orbitLayer.classList.add("active");
    void orbitRing.offsetWidth;
    orbitRing.classList.add("spin");
    orbitRing.querySelectorAll(".orbit-node").forEach((node) => node.classList.add("node-fly"));
    vibrate(15);

    const verificationRequest = fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
    }).then(async (response) => ({
      payload: await response.json(),
      status: response.status,
    })).catch(() => ({ networkError: true }));

    await new Promise((resolve) => window.setTimeout(resolve, ORBIT_DURATION + ORBIT_PAUSE));
    if (state !== "orbit") return;

    state = "checking";
    card.dataset.state = "checking";
    orbitLayer.classList.remove("active");
    orbitRing.classList.remove("spin");
    orbitRing.replaceChildren();
    inputStage.style.display = "none";
    title.textContent = form.dataset.loadingTitle;
    subtitle.textContent = form.dataset.loadingSubtitle;
    loadingWrap.classList.add("active");
    loadingWrap.setAttribute("aria-hidden", "false");
    animateProgress();

    const [result] = await Promise.all([
      verificationRequest,
      new Promise((resolve) => window.setTimeout(resolve, LOADING_DURATION)),
    ]);
    if (state !== "checking") return;
    setProgress(100);
    await new Promise((resolve) => window.setTimeout(resolve, 360));
    if (state !== "checking") return;

    if (result.networkError) {
      loadingWrap.classList.remove("active");
      loadingWrap.setAttribute("aria-hidden", "true");
      showError(form.dataset.networkMessage);
      return;
    }

    const payload = result.payload || {};
    if (payload.verified) {
      state = "success";
      card.dataset.state = "success";
      setProgress(100);
      loadingWrap.classList.remove("active");
      loadingWrap.setAttribute("aria-hidden", "true");
      successWrap.classList.add("active");
      successWrap.setAttribute("aria-hidden", "false");
      card.classList.add("success-tint");
      spawnSplash();
      vibrate([30, 40, 60]);

      window.setTimeout(() => {
        title.textContent = form.dataset.successTitle;
        subtitle.textContent = form.dataset.successSubtitle;
      }, 250);
      window.setTimeout(
        () => window.location.assign(payload.redirect || form.dataset.resetUrl),
        1750,
      );
      return;
    }

    loadingWrap.classList.remove("active");
    loadingWrap.setAttribute("aria-hidden", "true");
    showError(payload.message || form.dataset.errorMessage, payload.redirect);
  }

  function scheduleVerification() {
    window.clearTimeout(autoSubmitTimer);
    autoSubmitTimer = window.setTimeout(verify, 180);
  }

  digits.forEach((input, index) => {
    input.addEventListener("input", () => {
      if (state !== "idle" && state !== "error") return;
      if (state === "error") resetState(false);
      else {
        error.classList.remove("show");
        error.textContent = "";
      }

      const value = input.value.replace(/\D/g, "");
      if (value.length > 1) {
        distribute(value, index);
        return;
      }

      input.value = value.slice(-1);
      input.classList.toggle("filled", Boolean(input.value));
      syncFallback();
      vibrate(15);
      if (input.value && index < digits.length - 1) digits[index + 1].focus();
      if (digits.every((digit) => digit.value)) scheduleVerification();
    });

    input.addEventListener("paste", (event) => {
      const pasted = event.clipboardData?.getData("text") || "";
      if (!/\d/.test(pasted)) return;
      event.preventDefault();
      if (state === "error") resetState(false);
      distribute(pasted, index);
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Backspace") {
        if (state === "error") resetState(false);
        if (!input.value && index > 0) digits[index - 1].focus();
      } else if (event.key === "ArrowLeft" && index > 0) {
        digits[index - 1].focus();
      } else if (event.key === "ArrowRight" && index < digits.length - 1) {
        digits[index + 1].focus();
      }
    });

    input.addEventListener("focus", () => {
      if (state === "error") resetState(false);
      input.select();
    });
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    verify();
  });

  document.addEventListener("pointermove", (event) => {
    if (event.pointerType !== "mouse" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    pointerLight.style.left = String(event.clientX) + "px";
    pointerLight.style.top = String(event.clientY) + "px";
    pointerLight.style.opacity = "1";
  });
  document.addEventListener("pointerleave", () => { pointerLight.style.opacity = "0"; });

  window.setTimeout(() => digits[0].focus(), 300);
})();
