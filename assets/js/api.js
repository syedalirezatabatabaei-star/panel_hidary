"use strict";

function readStorage(key) {
  try { return localStorage.getItem(key); } catch (_) { return null; }
}

function normalizeApiBase(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function resolveApiBase() {
  const saved = readStorage("hidary_api");
  if (saved) return normalizeApiBase(saved);

  const host = window.location.hostname;
  const port = window.location.port;
  const isLocal = host === "localhost" || host === "127.0.0.1" || host === "::1";
  const isFile = window.location.protocol === "file:";
  if (isFile || (isLocal && port !== "8000")) {
    return "http://127.0.0.1:8000";
  }
  return normalizeApiBase(window.location.origin);
}

const API_BASE = resolveApiBase();
window.API_BASE = API_BASE;

function apiErrorMessage(data, status) {
  const detail = data && data.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    return detail.map(function (item) {
      return item && item.msg ? item.msg : String(item);
    }).join("؛ ");
  }
  if (data && typeof data.message === "string") return data.message;
  return "درخواست ناموفق بود (کد " + status + ")";
}

const api = {
  async request(path, options) {
    const opts = options || {};
    const headers = new Headers(opts.headers || {});
    const body = opts.body;

    if (body instanceof FormData) {
      headers.delete("Content-Type");
    } else if (body instanceof URLSearchParams) {
      if (!headers.has("Content-Type")) {
        headers.set("Content-Type", "application/x-www-form-urlencoded;charset=UTF-8");
      }
    } else if (body !== undefined && body !== null && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    // Capture the token used by this request. A delayed 401 from an old
    // session must never erase a newer token issued by a successful login.
    const tokenUsed = readStorage("hidary_token");
    if (tokenUsed) headers.set("Authorization", "Bearer " + tokenUsed);
    if (!headers.has("Accept")) headers.set("Accept", "application/json");

    let response;
    try {
      response = await fetch(API_BASE + (String(path).startsWith("/") ? path : "/" + path), {
        ...opts,
        headers: headers,
        credentials: opts.credentials || "same-origin"
      });
    } catch (error) {
      throw new Error("ارتباط با سرور برقرار نشد. آدرس API: " + API_BASE);
    }

    let data = null;
    const contentType = response.headers.get("content-type") || "";
    if (response.status !== 204) {
      if (contentType.indexOf("application/json") !== -1 || contentType.indexOf("+json") !== -1) {
        data = await response.json().catch(function () { return null; });
      } else {
        data = await response.text().catch(function () { return ""; });
      }
    }

    if (!response.ok) {
      if (response.status === 401) {
        const currentToken = readStorage("hidary_token");
        // Act only if the failed request still belongs to the current session.
        // If login replaced the old token while this request was in flight,
        // ignore this stale 401 instead of logging the new session out.
        const sameSession = tokenUsed ? currentToken === tokenUsed : !currentToken;
        if (sameSession) {
          if (tokenUsed) {
            try { localStorage.removeItem("hidary_token"); } catch (_) {}
          }
          const pathName = window.location.pathname.toLowerCase();
          if (pathName.indexOf("/login") === -1) {
            window.location.replace("/login/");
          }
        }
      }
      throw new Error(apiErrorMessage(data, response.status));
    }
    return data;
  },

  get(path) {
    return this.request(path, { method: "GET" });
  },

  post(path, body) {
    const payload = body instanceof FormData || body instanceof URLSearchParams
      ? body
      : JSON.stringify(body === undefined ? {} : body);
    return this.request(path, { method: "POST", body: payload });
  },

  put(path, body) {
    return this.request(path, { method: "PUT", body: JSON.stringify(body || {}) });
  },

  patch(path, body) {
    return this.request(path, { method: "PATCH", body: JSON.stringify(body || {}) });
  }
};

window.api = api;

function toast(message) {
  const node = document.getElementById("toast");
  if (!node) return;
  node.textContent = String(message || "");
  node.classList.add("show");
  if (node._hideTimer) window.clearTimeout(node._hideTimer);
  node._hideTimer = window.setTimeout(function () {
    node.classList.remove("show");
  }, 3200);
}

function esc(value) {
  return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, function (char) {
    return {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[char];
  });
}

function num(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toLocaleString("fa-IR") : "۰";
}

window.toast = toast;
window.esc = esc;
window.num = num;
