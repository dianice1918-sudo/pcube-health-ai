const TOKEN_KEY = "pcube_access_token";
const API_BASE_KEY = "pcube_api_base";
const SAME_ORIGIN_API_KEY = "pcube_same_origin_api";
const DEFAULT_API_PORT = "8000";
const LOCAL_API_PORTS = ["5500", "5501", "5502", "8000", "8001", "8002"];
const DEV_PORTS = new Set([
  "5500",
  "5501",
  "5502",
  "3000",
  "5173",
  "5174",
  "4173",
  "8080",
  "8081",
  "4200",
  "5000",
]);
const PAGE_ASSET_VERSION = "20260309b";
let authToken = localStorage.getItem(TOKEN_KEY) || "";

function isDevPort(port) {
  return DEV_PORTS.has(String(port || ""));
}

function sameOriginBase() {
  if (window.location.protocol === "file:") return "";
  return `${window.location.protocol}//${window.location.host}`.replace(
    /\/+$/,
    "",
  );
}

function isApiServedFrontend() {
  const path = String(window.location.pathname || "");
  return path.startsWith("/frontend/") || path.startsWith("/app/");
}

function isLocalStaticDevPage() {
  if (window.location.protocol === "file:") return true;
  if (
    window.location.hostname !== "127.0.0.1" &&
    window.location.hostname !== "localhost"
  ) {
    return false;
  }
  if (!isDevPort(window.location.port)) return false;
  return !isApiServedFrontend();
}

function shouldUseSameOriginApi() {
  const explicit = String(localStorage.getItem(SAME_ORIGIN_API_KEY) || "").trim();
  if (explicit === "1") return !isLocalStaticDevPage();
  if (explicit === "0") return false;
  if (window.location.protocol === "file:") return false;
  return isDevPort(window.location.port) && isApiServedFrontend();
}

function withPageVersion(target) {
  const raw = String(target || "").trim();
  if (!raw || /^(https?:|mailto:|tel:|#)/i.test(raw)) return raw;
  const hashIndex = raw.indexOf("#");
  const hashPart = hashIndex >= 0 ? raw.slice(hashIndex) : "";
  const base = hashIndex >= 0 ? raw.slice(0, hashIndex) : raw;
  if (!/\.html(\?|$)/i.test(base)) return raw;
  if (/[?&]v=/.test(base)) return raw;
  const separator = base.includes("?") ? "&" : "?";
  return `${base}${separator}v=${PAGE_ASSET_VERSION}${hashPart}`;
}

function normalizeApiBase(raw) {
  const cleaned = String(raw || "").trim();
  if (!cleaned) return "";
  try {
    const url = new URL(cleaned, window.location.origin);
    return `${url.protocol}//${url.host}${url.pathname}`.replace(/\/+$/, "");
  } catch {
    return "";
  }
}

function isLocalhostLikeHost(host) {
  const clean = String(host || "").toLowerCase();
  return clean === "localhost" || clean === "127.0.0.1" || clean === "0.0.0.0" || clean === "::1";
}

function deriveDevApiBase() {
  if (!isDevPort(window.location.port)) return "";
  const host = String(window.location.hostname || "");
  if (host && !["localhost", "127.0.0.1", "0.0.0.0", "::1"].includes(host)) {
    return `${window.location.protocol}//${host}:${DEFAULT_API_PORT}`;
  }
  return `http://127.0.0.1:${DEFAULT_API_PORT}`;
}

function resolveApiBase() {
  if (shouldUseSameOriginApi()) {
    const base = sameOriginBase();
    if (base) return base;
  }
  const configured = String(localStorage.getItem(API_BASE_KEY) || "").trim();
  const normalized = configured ? normalizeApiBase(configured) : "";
  const currentBase = sameOriginBase();
  if (normalized) {
    if (
      isLocalStaticDevPage() &&
      (() => {
        try {
          const normalizedUrl = new URL(normalized, window.location.origin);
          return (
            (currentBase && normalized === currentBase) ||
            (isLocalhostLikeHost(normalizedUrl.hostname) && isDevPort(normalizedUrl.port))
          );
        } catch {
          return false;
        }
      })()
    ) {
      return deriveDevApiBase();
    }
    return normalized;
  }
  if (configured) localStorage.removeItem(API_BASE_KEY);
  if (window.location.protocol === "file:") return "http://127.0.0.1:8000";
  if (isLocalStaticDevPage()) return deriveDevApiBase();
  return "";
}

function ensureApiBaseDefault() {
  if (shouldUseSameOriginApi()) {
    const base = sameOriginBase();
    if (base) {
      localStorage.setItem(API_BASE_KEY, base);
      return;
    }
  }
  if (isLocalStaticDevPage()) {
    localStorage.setItem(API_BASE_KEY, deriveDevApiBase());
    return;
  }
  const existing = String(localStorage.getItem(API_BASE_KEY) || "").trim();
  if (existing) return;
  if (window.location.protocol === "file:") {
    localStorage.setItem(
      API_BASE_KEY,
      deriveDevApiBase() || `http://127.0.0.1:${DEFAULT_API_PORT}`,
    );
    return;
  }
  const devBase = deriveDevApiBase();
  if (devBase) localStorage.setItem(API_BASE_KEY, devBase);
}

ensureApiBaseDefault();
let API_BASE = resolveApiBase();

function resolveCurrentOriginApiBase() {
  if (window.location.protocol === "file:") return "";
  if (!isLocalhostLikeHost(window.location.hostname)) return "";
  return `${window.location.protocol}//${window.location.host}`.replace(
    /\/+$/,
    "",
  );
}

function buildApiCandidates() {
  const protocol = window.location.protocol || "http:";
  const candidates = [];
  const host = String(window.location.hostname || "");
  const port = String(window.location.port || "");
  const isLocalHost = isLocalhostLikeHost(host);

  if (isLocalHost) {
    candidates.push(resolveCurrentOriginApiBase());
    if (host && host !== "0.0.0.0") {
      for (const candidatePort of LOCAL_API_PORTS) {
        if (String(candidatePort) !== port) {
          candidates.push(`${protocol}//${host}:${candidatePort}`);
        }
      }
    }
    for (const localHost of ["127.0.0.1", "localhost"]) {
      for (const candidatePort of LOCAL_API_PORTS) {
        candidates.push(`${protocol}//${localHost}:${candidatePort}`);
      }
    }
  } else if (host && port !== DEFAULT_API_PORT) {
    candidates.push(`${protocol}//${host}:${DEFAULT_API_PORT}`);
  }

  return [...new Set(candidates.filter(Boolean))];
}

function toApiUrl(path) {
  const normalized = String(path || "").startsWith("/")
    ? String(path)
    : `/${String(path || "")}`;
  return API_BASE ? `${API_BASE}${normalized}` : normalized;
}

function shouldAutoSwitchToBackendHostedPage() {
  if (!API_BASE || !isLocalStaticDevPage()) return false;
  return (
    window.location.port === "5500" ||
    window.location.port === "5501" ||
    window.location.port === "5502"
  );
}

function backendHostedFrontendUrl(target) {
  const raw = String(target || "").trim();
  if (!raw || !API_BASE || /^(https?:|mailto:|tel:|#)/i.test(raw)) return raw;
  const safeTarget = raw.replace(/^\/+/, "").replace(/^frontend\/assets\//i, "");
  return `${API_BASE}/frontend/assets/${safeTarget}`;
}

async function isBackendReachable(timeoutMs = 1200) {
  if (!API_BASE) return false;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}/healthz`, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}

async function frontendPageUrl(target) {
  const versioned = withPageVersion(target);
  if (!versioned) return versioned;
  if (shouldAutoSwitchToBackendHostedPage()) {
    const backendReady = await isBackendReachable();
    if (backendReady) return backendHostedFrontendUrl(versioned);
  }
  return versioned;
}

function currentFrontendPageTarget() {
  const path = String(window.location.pathname || "");
  const match = path.match(/(?:^|\/)frontend\/assets\/([^?#]+)/i);
  const page = match ? match[1] : path.split("/").pop();
  if (!page || !/\.html$/i.test(page)) return "";
  return `${page}${window.location.search || ""}${window.location.hash || ""}`;
}

async function maybeSwitchToBackendHostedPage() {
  if (!shouldAutoSwitchToBackendHostedPage()) return false;
  const currentTarget = currentFrontendPageTarget();
  if (!currentTarget) return false;
  const backendReady = await isBackendReachable();
  if (!backendReady) return false;
  const target = backendHostedFrontendUrl(currentTarget);
  if (target && !window.location.href.startsWith(target)) {
    window.location.replace(target);
    return true;
  }
  return false;
}

const authStateEl = document.getElementById("authState");
const enableLocationBtn = document.getElementById("enableLocationBtn");
const disableLocationBtn = document.getElementById("disableLocationBtn");
const continueToDashboardBtn = document.getElementById(
  "continueToDashboardBtn",
);
const skipToDashboardBtn = document.getElementById("skipToDashboardBtn");
const logoutBtn = document.getElementById("logoutBtn");
const userMenuBtn = document.getElementById("userMenuBtn");
const userMenuPanel = document.getElementById("userMenuPanel");
const locationOut = document.getElementById("locationOut");

if (!authToken) {
  frontendPageUrl("login.html").then((target) => {
    window.location.replace(target || withPageVersion("login.html"));
  });
}

function setAuthState() {
  if (!authStateEl) return;
  authStateEl.textContent = authToken ? "Authenticated" : "Not signed in";
}

function pretty(data) {
  return JSON.stringify(data, null, 2);
}

function formatDateTimeLocal(value) {
  if (!value) return "N/A";
  const raw = String(value);
  const withTz = /Z|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`;
  const d = new Date(withTz);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function prettyLocation(data, extraText = "") {
  const granted = Boolean(data?.location_permission_granted);
  const monitoring = Boolean(data?.region_monitoring_enabled);
  const updated = data?.location_updated_at
    ? formatDateTimeLocal(data.location_updated_at)
    : "N/A";
  const statusMsg =
    String(data?.status_message || "").trim() ||
    (monitoring
      ? "Regional health safety alerts are active."
      : granted
        ? "Permission granted. Waiting for region sync."
        : "Location access is disabled.");
  return [
    `Location Access: ${granted ? "Granted" : "Disabled"}`,
    `Regional Monitoring: ${monitoring ? "Enabled" : "Not active"}`,
    `Last Updated: ${updated}`,
    `Status: ${statusMsg}`,
    extraText ? `Info: ${extraText}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function explainGeoError(err) {
  const code = Number(err?.code || 0);
  if (code === 1) {
    return "Location access was denied in your browser/device settings.";
  }
  if (code === 2) {
    return "Location is currently unavailable. Check GPS/network and try again.";
  }
  if (code === 3) {
    return "Location request timed out. Try again with better signal.";
  }
  const message = String(err?.message || "").trim();
  return message || "Failed to read device location.";
}

function logoutToLogin() {
  closeUserMenu();
  authToken = "";
  localStorage.removeItem(TOKEN_KEY);
  setAuthState();
  frontendPageUrl("login.html").then((target) => {
    window.location.replace(target || withPageVersion("login.html"));
  });
}

function setUserMenuOpen(isOpen) {
  if (!userMenuBtn || !userMenuPanel) return;
  const open = Boolean(isOpen);
  userMenuPanel.classList.toggle("hidden", !open);
  userMenuBtn.setAttribute("aria-expanded", open ? "true" : "false");
}

function closeUserMenu() {
  setUserMenuOpen(false);
}

function toggleUserMenu() {
  if (!userMenuBtn || !userMenuPanel) return;
  const willOpen = userMenuPanel.classList.contains("hidden");
  setUserMenuOpen(willOpen);
}

async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && authToken) headers["Authorization"] = `Bearer ${authToken}`;
  const apiKey = String(localStorage.getItem("pcube_api_key") || "").trim();
  if (apiKey) headers["X-API-Key"] = apiKey;

  const normalizedPath = String(path || "").startsWith("/")
    ? String(path)
    : `/${String(path || "")}`;
  const requestInit = {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };
  let res;
  const url = toApiUrl(normalizedPath);
  try {
    res = await fetch(url, requestInit);
  } catch {
    if (normalizedPath.startsWith("/")) {
      const candidates = buildApiCandidates().filter((base) => base !== API_BASE);
      for (const base of candidates) {
        try {
          const health = await fetch(`${base}/healthz`, {
            method: "GET",
            cache: "no-store",
          });
          if (!health.ok) continue;
          res = await fetch(`${base}${normalizedPath}`, requestInit);
          API_BASE = base;
          localStorage.setItem(API_BASE_KEY, base);
          break;
        } catch {
          // Try next candidate.
        }
      }
    }
    if (!res && typeof navigator !== "undefined" && navigator.onLine === false) {
      throw new Error("No internet connection. Please check your network and try again.");
    }
    if (!res) {
      throw new Error("Unable to connect right now. Please try again in a moment.");
    }
  }
  const contentType = res.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await res.json()
    : await res.text();
  if (!res.ok) {
    if (res.status === 401 && auth) {
      logoutToLogin();
      throw new Error("Session expired. Please login again.");
    }
    const detail =
      typeof payload === "string" ? payload : payload.detail || pretty(payload);
    throw new Error(`${res.status}: ${detail}`);
  }
  return payload;
}

async function loadLocation() {
  try {
    const data = await api("/users/me/location");
    if (locationOut) locationOut.textContent = prettyLocation(data);
  } catch (err) {
    if (locationOut) locationOut.textContent = err.message;
  }
}

enableLocationBtn?.addEventListener("click", async () => {
  if (!navigator.geolocation) {
    if (locationOut)
      locationOut.textContent = "Geolocation is not available in this browser.";
    return;
  }
  try {
    const pos = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 12000,
      });
    });
    const lat = pos.coords.latitude;
    const lon = pos.coords.longitude;
    const capturedAt = new Date();
    await api("/users/me/location-permission", {
      method: "PATCH",
      body: { granted: true },
    });
    const updated = await api("/users/me/location", {
      method: "PUT",
      body: { latitude: lat, longitude: lon, label: "local region" },
    });
    if (locationOut) {
      locationOut.textContent = prettyLocation(
        updated,
        `Device sync time: ${formatDateTimeLocal(capturedAt.toISOString())}`,
      );
    }
  } catch (err) {
    const geoReason = explainGeoError(err);
    if (locationOut) {
      locationOut.textContent = [
        "Regional monitoring is not active yet.",
        `Reason: ${geoReason}`,
        "Action: allow location access and click Enable Location again.",
      ].join("\n");
    }
  }
});

disableLocationBtn?.addEventListener("click", async () => {
  try {
    const data = await api("/users/me/location-permission", {
      method: "PATCH",
      body: { granted: false },
    });
    if (locationOut) locationOut.textContent = prettyLocation(data);
  } catch (err) {
    if (locationOut) locationOut.textContent = err.message;
  }
});

continueToDashboardBtn?.addEventListener("click", async () => {
  window.location.href =
    (await frontendPageUrl("dashboard.html")) || withPageVersion("dashboard.html");
});

skipToDashboardBtn?.addEventListener("click", async () => {
  window.location.href =
    (await frontendPageUrl("dashboard.html")) || withPageVersion("dashboard.html");
});

userMenuBtn?.addEventListener("click", (event) => {
  event.preventDefault();
  event.stopPropagation();
  toggleUserMenu();
});
userMenuPanel?.addEventListener("click", (event) => {
  event.stopPropagation();
});
document.addEventListener("click", (event) => {
  if (!userMenuBtn || !userMenuPanel) return;
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (userMenuBtn.contains(target) || userMenuPanel.contains(target)) return;
  closeUserMenu();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeUserMenu();
});
logoutBtn?.addEventListener("click", logoutToLogin);

setAuthState();
(async () => {
  if (await maybeSwitchToBackendHostedPage()) return;
  loadLocation();
})();
