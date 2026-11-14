"use strict";

(function () {
  const form = document.getElementById("loginForm");
  if (!form) return;

  const usernameInput = document.getElementById("username");
  const passwordInput = document.getElementById("password");
  const errorBox = document.getElementById("error");
  const submitButton = form.querySelector('button[type="submit"]');
  const toggleButton = document.getElementById("togglePassword");

  let loginInProgress = false;

  function showError(message) {
    if (errorBox) errorBox.textContent = message || "";
  }

  if (toggleButton && passwordInput) {
    // One source of truth for the visual state: button class + input type.
    toggleButton.addEventListener("click", function () {
      const shouldShow = passwordInput.type === "password";
      passwordInput.type = shouldShow ? "text" : "password";
      toggleButton.classList.toggle("is-visible", shouldShow);
      toggleButton.setAttribute("aria-label", shouldShow ? "پنهان کردن رمز عبور" : "نمایش رمز عبور");
      toggleButton.setAttribute("aria-pressed", String(shouldShow));
    });
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (loginInProgress) return;
    loginInProgress = true;
    showError("");

    const username = usernameInput ? usernameInput.value.trim() : "";
    const password = passwordInput ? passwordInput.value : "";
    if (!username || !password) {
      loginInProgress = false;
      showError("نام کاربری و رمز عبور را وارد کنید.");
      return;
    }

    const originalLabel = submitButton ? submitButton.textContent : "";
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "در حال بررسی...";
    }

    try {
      const payload = new URLSearchParams();
      payload.set("username", username);
      payload.set("password", password);

      const result = await window.api.post("/api/auth/login", payload);
      if (!result || !result.success) {
        throw new Error("پاسخ ورود از سرور معتبر نیست.");
      }
      window.location.assign("/dashboard/");
    } catch (error) {
      showError(error && error.message ? error.message : "ورود ناموفق بود.");
      loginInProgress = false;
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = originalLabel || "ورود به سامانه";
      }
    }
  });

  // Keep an existing valid session shortcut, but never let this background
  // check interfere with a login the user has just submitted.
  window.api.get("/api/auth/me").then(function () {
    if (!loginInProgress) window.location.replace("/dashboard/");
  }).catch(function () {});
})();
