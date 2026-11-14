"use strict";

(function () {
  const form = document.getElementById("loginForm");
  if (!form) return;

  const usernameInput = document.getElementById("username");
  const passwordInput = document.getElementById("password");
  const errorBox = document.getElementById("error");
  const submitButton = form.querySelector('button[type="submit"]');
  const toggleButton = document.getElementById("togglePassword");

  function showError(message) {
    if (errorBox) errorBox.textContent = message || "";
  }

  if (toggleButton && passwordInput) {
    toggleButton.addEventListener("click", function () {
      const visible = passwordInput.type === "password";
      passwordInput.type = visible ? "text" : "password";
      toggleButton.setAttribute("aria-label", visible ? "پنهان کردن رمز عبور" : "نمایش رمز عبور");
      toggleButton.setAttribute("aria-pressed", String(visible));
      const openIcon = toggleButton.querySelector(".eye-open");
      const closedIcon = toggleButton.querySelector(".eye-closed");
      if (openIcon) openIcon.hidden = visible;
      if (closedIcon) closedIcon.hidden = !visible;
    });
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    showError("");

    const username = usernameInput ? usernameInput.value.trim() : "";
    const password = passwordInput ? passwordInput.value : "";
    if (!username || !password) {
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
      if (!result || !result.access_token) {
        throw new Error("پاسخ ورود از سرور معتبر نیست.");
      }

      localStorage.setItem("hidary_token", result.access_token);
      window.location.assign("/dashboard/");
    } catch (error) {
      showError(error && error.message ? error.message : "ورود ناموفق بود.");
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = originalLabel || "ورود به سامانه";
      }
    }
  });

  const existingToken = (function () {
    try { return localStorage.getItem("hidary_token"); } catch (_) { return null; }
  })();

  if (existingToken) {
    window.api.get("/api/auth/me").then(function () {
      window.location.replace("/dashboard/");
    }).catch(function () {
      // توکن نامعتبر پاک می‌شود؛ کاربر می‌تواند دوباره وارد شود.
    });
  }
})();
