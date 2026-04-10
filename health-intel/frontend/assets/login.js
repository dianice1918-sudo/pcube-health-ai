const TOKEN_KEY = "pcube_access_token";
const API_BASE_KEY = "pcube_api_base";
const FORCE_STATIC_FRONTEND_KEY = "pcube_use_static_frontend";
const BACKEND_AUTH_REDIRECT_KEY = "pcube_use_backend_auth_pages";
const API_BASE_META_NAME = "pcube-api-base";
const API_BASE_PARAM_NAME = "api_base";
const SAME_ORIGIN_API_KEY = "pcube_same_origin_api";
const OTP_SESSION_KEY = "pcube_login_otp_session";
const OTP_CREDENTIALS_KEY = "pcube_login_otp_credentials";
const OTP_EMAIL_KEY = "pcube_login_email";
const OTP_SESSION_TTL_MS = 10 * 60 * 1000;
const DEFAULT_API_PORT = "8000";
const LOCAL_API_PORTS = ["5500", "5501", "5502", "8000", "8001", "8002"];
const OTP_REQUIRED_ERROR_FRAGMENT = "OTP verification required";
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

let loginChallengeId = "";
let lastLoginCredentials = null;
const OTP_REGEX = /^\d{4,8}$/;

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
  if (window.location.protocol !== "file:" && !isLocalhostLikeHost(window.location.hostname)) {
    return true;
  }
  if (explicit === "1") return !isLocalStaticDevPage();
  if (explicit === "0") return false;
  if (window.location.protocol === "file:") return false;
  return isDevPort(window.location.port) && isApiServedFrontend();
}

function seedSameOriginPreference() {
  if (localStorage.getItem(SAME_ORIGIN_API_KEY) != null) return;
  if (window.location.protocol === "file:") return;
  if (isDevPort(window.location.port) && isApiServedFrontend()) {
    localStorage.setItem(SAME_ORIGIN_API_KEY, "1");
  } else if (isLocalStaticDevPage()) {
    localStorage.setItem(SAME_ORIGIN_API_KEY, "0");
  }
}

function isIpAddress(host) {
  return /^\d{1,3}(\.\d{1,3}){3}$/.test(String(host || ""));
}

function isPrivateIp(host) {
  if (!isIpAddress(host)) return false;
  const [a, b] = String(host)
    .split(".")
    .map((part) => Number(part));
  if (a === 10) return true;
  if (a === 127) return true;
  if (a === 192 && b === 168) return true;
  if (a === 172 && b >= 16 && b <= 31) return true;
  return false;
}

function isLocalhostLikeHost(host) {
  const clean = String(host || "").toLowerCase();
  return (
    clean === "localhost" ||
    clean === "127.0.0.1" ||
    clean === "0.0.0.0" ||
    clean === "::1" ||
    isPrivateIp(clean)
  );
}

function deriveDevApiBase() {
  if (!isDevPort(window.location.port)) return "";
  return `http://127.0.0.1:${DEFAULT_API_PORT}`;
}

function normalizeApiBase(raw) {
  const cleaned = String(raw || "").trim();
  if (!cleaned) return "";
  try {
    const url = new URL(cleaned, window.location.origin);
    const normalized = `${url.protocol}//${url.host}${url.pathname}`.replace(/\/+$/, "");
    return normalized;
  } catch {
    return "";
  }
}

function persistApiBase(raw) {
  const normalized = normalizeApiBase(raw);
  if (!normalized) return "";
  localStorage.setItem(API_BASE_KEY, normalized);
  return normalized;
}

function readApiBaseFromQuery() {
  try {
    const search = new URLSearchParams(window.location.search || "");
    const hinted = search.get(API_BASE_PARAM_NAME);
    return normalizeApiBase(hinted);
  } catch {
    return "";
  }
}

function readApiBaseFromMeta() {
  const meta = document.querySelector(`meta[name="${API_BASE_META_NAME}"]`);
  if (!meta) return "";
  return normalizeApiBase(meta.getAttribute("content"));
}

function readApiBaseFromGlobals() {
  const hinted =
    window.PCUBE_API_BASE ||
    window.__PCUBE_API_BASE__ ||
    window.pcubeApiBase ||
    "";
  return normalizeApiBase(hinted);
}

function ensureApiBaseDefault() {
  if (isLocalStaticDevPage()) {
    localStorage.setItem(API_BASE_KEY, deriveDevApiBase() || "http://127.0.0.1:8000");
    return;
  }
  if (shouldUseSameOriginApi()) {
    const base = sameOriginBase();
    if (base) {
      localStorage.setItem(API_BASE_KEY, base);
      return;
    }
  }
  const existing = String(localStorage.getItem(API_BASE_KEY) || "").trim();
  if (existing) return;
  if (window.location.protocol === "file:") {
    localStorage.setItem(API_BASE_KEY, "http://127.0.0.1:8000");
    return;
  }
  const devBase = deriveDevApiBase();
  if (devBase) {
    localStorage.setItem(API_BASE_KEY, devBase);
  }
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
      return deriveDevApiBase() || "http://127.0.0.1:8000";
    }
    return normalized;
  }
  if (configured) {
    localStorage.removeItem(API_BASE_KEY);
  }
  if (window.location.protocol === "file:") return "http://127.0.0.1:8000";
  if (isLocalStaticDevPage()) return deriveDevApiBase() || "http://127.0.0.1:8000";
  const devBase = deriveDevApiBase();
  if (devBase) return devBase;
  return "";
}

function resolveCurrentOriginApiBase() {
  if (window.location.protocol === "file:") return "";
  if (!isLocalhostLike()) return "";
  return `${window.location.protocol}//${window.location.host}`.replace(
    /\/+$/,
    "",
  );
}

function isLocalhostLike() {
  return isLocalhostLikeHost(window.location.hostname);
}

function buildApiCandidates() {
  const protocol = window.location.protocol || "http:";
  const candidates = [];
  const host = String(window.location.hostname || "");
  const port = String(window.location.port || "");

  if (isLocalhostLike()) {
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
  } else {
    if (host && port !== DEFAULT_API_PORT) {
      candidates.push(`${protocol}//${host}:${DEFAULT_API_PORT}`);
    }
    const trimmed = host.replace(/^app\./i, "").replace(/^www\./i, "");
    if (trimmed && trimmed !== host) {
      candidates.push(`${protocol}//api.${trimmed}`);
    }
    const pieces = trimmed.split(".");
    if (pieces.length >= 2) {
      const root = pieces.slice(-2).join(".");
      candidates.push(`${protocol}//api.${root}`);
    }
  }
  return [...new Set(candidates.filter(Boolean))];
}

async function probeApiBaseCandidates(preferredBases = []) {
  const ordered = [...new Set([...preferredBases, ...buildApiCandidates()].filter(Boolean))];
  for (const base of ordered) {
    try {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), 1500);
      try {
        const health = await fetch(`${base}/healthz`, {
          method: "GET",
          cache: "no-store",
          signal: controller.signal,
        });
        if (health.ok) return base;
      } finally {
        window.clearTimeout(timer);
      }
    } catch {
      // Try the next candidate.
    }
  }
  return "";
}

async function tryApiBaseCandidates(normalizedPath, requestInit, disallowedBases) {
  const skip = new Set((disallowedBases || []).filter(Boolean));
  const candidates = buildApiCandidates().filter((base) => !skip.has(base));
  for (const base of candidates) {
    try {
      const health = await fetch(`${base}/healthz`, {
        method: "GET",
        cache: "no-store",
      });
      if (!health.ok) continue;
      const candidateResponse = await fetch(`${base}${normalizedPath}`, requestInit);
      if (
        candidateResponse.ok ||
        ![404, 405, 501].includes(candidateResponse.status)
      ) {
        API_BASE = base;
        localStorage.setItem(API_BASE_KEY, base);
        return candidateResponse;
      }
    } catch {
      // Try next candidate.
    }
  }
  return null;
}

let API_BASE = "";
async function bootstrapApiBase() {
  seedSameOriginPreference();
  const hinted =
    readApiBaseFromQuery() || readApiBaseFromMeta() || readApiBaseFromGlobals();
  if (hinted) {
    localStorage.setItem(SAME_ORIGIN_API_KEY, "0");
    persistApiBase(hinted);
  } else {
    ensureApiBaseDefault();
  }
  API_BASE = resolveApiBase();
  const liveBase = await probeApiBaseCandidates(API_BASE ? [API_BASE] : []);
  if (liveBase) {
    API_BASE = liveBase;
    localStorage.setItem(API_BASE_KEY, liveBase);
    if (liveBase !== sameOriginBase()) {
      localStorage.setItem(SAME_ORIGIN_API_KEY, "0");
    }
  } else if (!API_BASE) {
    const devBase = deriveDevApiBase();
    if (devBase) {
      API_BASE = devBase;
      localStorage.setItem(API_BASE_KEY, devBase);
    }
  }
}

function persistLoginEmail(email) {
  const clean = String(email || "").trim();
  if (!clean) return;
  localStorage.setItem(OTP_EMAIL_KEY, clean);
}

function restoreLoginEmail() {
  const stored = String(localStorage.getItem(OTP_EMAIL_KEY) || "").trim();
  if (!stored) return;
  const emailInput = document.getElementById("login-email");
  if (emailInput && !emailInput.value) emailInput.value = stored;
}

function clearOtpSession() {
  localStorage.removeItem(OTP_SESSION_KEY);
}

function clearOtpCredentials() {
  sessionStorage.removeItem(OTP_CREDENTIALS_KEY);
}

function persistOtpCredentials({ email, password } = {}) {
  const cleanEmail = String(email || "").trim();
  const cleanPassword = String(password || "");
  if (!cleanEmail || !cleanPassword) return;
  const record = {
    email: cleanEmail,
    password: cleanPassword,
    created_at: Date.now(),
  };
  sessionStorage.setItem(OTP_CREDENTIALS_KEY, JSON.stringify(record));
}

function readOtpCredentials() {
  const raw = sessionStorage.getItem(OTP_CREDENTIALS_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    const email = String(parsed?.email || "").trim();
    const password = String(parsed?.password || "");
    const createdAt = Number(parsed?.created_at || 0);
    if (!email || !password || !createdAt) throw new Error("Invalid OTP credentials");
    if (Date.now() - createdAt > OTP_SESSION_TTL_MS) {
      clearOtpCredentials();
      return null;
    }
    return { email, password, createdAt };
  } catch {
    clearOtpCredentials();
    return null;
  }
}

function persistOtpSession({ challengeId, email, destinationMasked, flow } = {}) {
  const cleanId = String(challengeId || "").trim();
  if (!cleanId) return;
  const record = {
    challenge_id: cleanId,
    email: String(email || "").trim(),
    destination_masked: String(destinationMasked || "").trim(),
    flow: String(flow || "login").trim().toLowerCase() === "signup" ? "signup" : "login",
    created_at: Date.now(),
  };
  localStorage.setItem(OTP_SESSION_KEY, JSON.stringify(record));
  if (record.email) persistLoginEmail(record.email);
}

function readOtpSession() {
  const raw = localStorage.getItem(OTP_SESSION_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    const challengeId = String(parsed?.challenge_id || "").trim();
    const createdAt = Number(parsed?.created_at || 0);
    const email = String(parsed?.email || "").trim();
    const destinationMasked = String(parsed?.destination_masked || "").trim();
    const flow =
      String(parsed?.flow || "").trim().toLowerCase() === "signup"
        ? "signup"
        : "login";
    if (!challengeId || !createdAt) throw new Error("Invalid OTP session");
    if (Date.now() - createdAt > OTP_SESSION_TTL_MS) {
      clearOtpSession();
      clearOtpCredentials();
      return null;
    }
    return { challengeId, email, destinationMasked, flow, createdAt };
  } catch {
    clearOtpSession();
    clearOtpCredentials();
    return null;
  }
}

function toApiUrl(path) {
  const normalized = String(path || "").startsWith("/")
    ? String(path)
    : `/${String(path || "")}`;
  return API_BASE ? `${API_BASE}${normalized}` : normalized;
}

function shouldAutoSwitchToBackendHostedPage() {
  if (localStorage.getItem(FORCE_STATIC_FRONTEND_KEY) === "1") return false;
  const explicitOptIn =
    localStorage.getItem(BACKEND_AUTH_REDIRECT_KEY) === "1" ||
    new URLSearchParams(window.location.search).get("backend_auth") === "1";
  if (!explicitOptIn) return false;
  if (!API_BASE) return false;
  if (
    !(
      window.location.hostname === "127.0.0.1" ||
      window.location.hostname === "localhost"
    )
  )
    return false;
  return (
    window.location.port === "5500" ||
    window.location.port === "5501" ||
    window.location.port === "5502"
  );
}

function backendHostedFrontendUrl(target) {
  const raw = String(target || "").trim();
  if (!raw || !API_BASE || /^(https?:|mailto:|tel:|#)/i.test(raw)) return raw;
  const cleanTarget = raw
    .replace(/^\/+/, "")
    .replace(/^frontend\/assets\//i, "")
    .replace(/^assets\//i, "");
  const [pathname, suffix = ""] = cleanTarget.split(/([?#].*)/, 2);
  const normalizedPath = String(pathname || "").trim();
  const routeTarget = normalizedPath.replace(/\.html$/i, "");
  if (!routeTarget || routeTarget === "pcube" || routeTarget === "index") {
    return `${API_BASE}/app/${suffix}`;
  }
  return `${API_BASE}/app/${routeTarget}${suffix}`;
}

function backendHostedAuthUrl(page) {
  const safePage =
    page === "signup"
      ? "signup.html"
      : page === "otp"
        ? "otp.html"
        : "login.html";
  return backendHostedFrontendUrl(safePage);
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

async function resolvePreferredFrontendUrl(target) {
  const raw = String(target || "").trim();
  if (!raw) return raw;
  if (/^(https?:|mailto:|tel:|#)/i.test(raw)) return raw;
  if (shouldAutoSwitchToBackendHostedPage()) {
    const backendReady = await isBackendReachable();
    if (backendReady) return backendHostedFrontendUrl(raw);
  }
  return raw;
}

function showForm(targetId) {
  document
    .querySelectorAll(".form-box")
    .forEach((el) => el.classList.remove("active"));
  const target = document.getElementById(targetId);
  if (target) target.classList.add("active");
}

function setMessage(text, state = "info") {
  const out = document.getElementById("authOut");
  if (!out) return;
  out.textContent = String(text || "");
  out.dataset.state = state;
}

function setRedirectingState(target, active) {
  if (!target) return;
  target.classList.toggle("redirecting", Boolean(active));
}

function setSubmitBusy(target, active, busyLabel, idleLabel) {
  if (!target) return;
  target.disabled = Boolean(active);
  setRedirectingState(target, active);
  setRedirectLabel(target, active ? busyLabel : idleLabel);
}

function setRedirectLabel(target, text) {
  if (!target) return;
  const label = target.querySelector(".redirect-label");
  if (label) label.textContent = text;
}

function bindRedirectLinks() {
  const redirectLinks = document.querySelectorAll(".switch-text a");
  redirectLinks.forEach((link) => {
    link.addEventListener("click", () => {
      setRedirectingState(link, true);
    });
  });
}

function buildBackendUnavailableMessage() {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return "No internet connection. Please check your network and try again.";
  }
  return "Unable to connect right now. Please try again in a moment.";
}

function isOtpRequiredError(err) {
  return (
    Number(err?.status || 0) === 403 &&
    String(err?.message || "").includes(OTP_REQUIRED_ERROR_FRAGMENT)
  );
}

function getOtpFlow(pageHint) {
  const queryFlow = new URLSearchParams(window.location.search || "").get("flow");
  const normalized = String(pageHint || queryFlow || "").trim().toLowerCase();
  return normalized === "signup" ? "signup" : "login";
}

function buildOtpPageUrl(flow = "login") {
  const params = new URLSearchParams();
  params.set("flow", getOtpFlow(flow));
  return `otp.html?${params.toString()}`;
}

function updateOtpPageContext(session = null) {
  const flow = getOtpFlow(session?.flow);
  const lead = document.getElementById("otpLead");
  const destination = document.getElementById("otpDestinationLabel");
  const backLink = document.getElementById("otpBackLink");
  const masked = session?.destinationMasked || session?.email || "your email";

  if (lead) {
    lead.textContent =
      flow === "signup"
        ? "Your account is almost ready. Enter the one-time code we sent to finish setup."
        : "This account still needs its one-time verification. Enter the code we sent to continue.";
  }
  if (destination) {
    destination.textContent = `Verification code sent to ${masked}.`;
  }
  if (backLink) {
    backLink.href = flow === "signup" ? "signup.html" : "login.html";
    setRedirectLabel(
      backLink,
      flow === "signup" ? "Back to sign up" : "Back to sign in",
    );
  }
}

function updateApiBaseHintLabel(customText) {
  const display = document.getElementById("apiBaseHint");
  if (!display) return;
  const label = customText || API_BASE || "(not set)";
  display.textContent = label;
}

function restoreOtpSession() {
  restoreLoginEmail();
  const session = readOtpSession();
  if (!session) return false;
  loginChallengeId = session.challengeId;
  updateOtpPageContext(session);
  showOtpPanel(true);
  validateOtpField();
  setMessage("Verification code already sent. Enter it to continue.", "info");
  return true;
}

async function promptForApiBaseChange() {
  const suggested = API_BASE || "http://127.0.0.1:8000";
  const input = window.prompt(
    "Enter backend API base URL (example: https://api.yourdomain.com)",
    suggested,
  );
  if (input === null) return;
  const normalized = persistApiBase(input);
  if (!normalized) {
    setMessage(
      "Enter a valid API base URL (e.g., https://api.example.com).",
      "error",
    );
    return;
  }
  API_BASE = normalized;
  updateApiBaseHintLabel();
  try {
    const health = await fetch(`${API_BASE}/healthz`, {
      method: "GET",
      cache: "no-store",
    });
    if (!health.ok) throw new Error(`Health check failed (${health.status})`);
    setMessage(`Connected to ${API_BASE}. Continue with login.`, "success");
  } catch (err) {
    setMessage(
      `Saved API base but cannot reach backend: ${err.message}`,
      "error",
    );
  }
}

function setupNavToggle() {
  const navToggle = document.querySelector(".nav-toggle");
  const primaryNav = document.getElementById("primary-navigation");
  if (!navToggle || !primaryNav) return;
  navToggle.addEventListener("click", () => {
    const expanded = navToggle.getAttribute("aria-expanded") === "true";
    navToggle.setAttribute("aria-expanded", String(!expanded));
    primaryNav.classList.toggle("open");
  });
}

function bindPasswordToggles() {
  document.querySelectorAll("[data-toggle-password]").forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.getAttribute("data-toggle-password");
      const input = targetId ? document.getElementById(targetId) : null;
      if (!input) return;
      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      button.textContent = reveal ? "Hide" : "Show";
      button.setAttribute(
        "aria-label",
        `${reveal ? "Hide" : "Show"} ${input.name.replace(/_/g, " ")}`,
      );
    });
  });
}

function validateSignupPayload(payload) {
  const fullName = String(payload?.full_name || "").trim();
  const email = String(payload?.email || "").trim();
  const password = String(payload?.password || "");
  const confirmPassword = String(payload?.confirm_password || "");

  if (!fullName || !email || !password || !confirmPassword) {
    return "Full name, email, and both password fields are required.";
  }
  if (password !== confirmPassword) {
    return "Passwords do not match.";
  }
  if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
    return "Password must be at least 8 characters and include letters and numbers.";
  }
  return "";
}

async function api(path, { method = "GET", body, auth = true } = {}) {
  const token = localStorage.getItem(TOKEN_KEY) || "";
  const apiKey = String(localStorage.getItem("pcube_api_key") || "").trim();
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && token) headers["Authorization"] = `Bearer ${token}`;
  if (apiKey) headers["X-API-Key"] = apiKey;

  let response;
  const normalizedPath = String(path || "").startsWith("/")
    ? String(path)
    : `/${String(path || "")}`;
  const url = toApiUrl(normalizedPath);
  const requestInit = {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };
  try {
    response = await fetch(url, requestInit);
  } catch {
    const fallbackBase = resolveCurrentOriginApiBase();
    const shouldTryFallback =
      Boolean(fallbackBase) &&
      fallbackBase !== API_BASE &&
      normalizedPath.startsWith("/") &&
      !isLocalStaticDevPage();
    if (shouldTryFallback) {
      const fallbackUrl = `${fallbackBase}${normalizedPath}`;
      try {
        response = await fetch(fallbackUrl, requestInit);
        API_BASE = fallbackBase;
        localStorage.setItem(API_BASE_KEY, fallbackBase);
      } catch {
        // Keep original network error below.
      }
    }
    if (!response && normalizedPath.startsWith("/")) {
      response = await tryApiBaseCandidates(normalizedPath, requestInit, [
        API_BASE,
        fallbackBase,
      ]);
    }
    if (!response) {
      throw new Error(buildBackendUnavailableMessage(url));
    }
  }

  if (!response.ok) {
    if ([404, 405, 501].includes(response.status) && normalizedPath.startsWith("/")) {
      const switchedResponse = await tryApiBaseCandidates(normalizedPath, requestInit, [API_BASE]);
      if (switchedResponse) {
        response = switchedResponse;
      }
    }
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail =
      typeof payload === "string"
        ? payload
        : payload?.detail || JSON.stringify(payload);
    const error = new Error(`${response.status}: ${detail}`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function showOtpPanel(show) {
  const panel = document.getElementById("otpPanel");
  const otpInput = document.getElementById("otpCodeInput");
  const verifyBtn = document.getElementById("verifyCodeBtn");
  const resendBtn = document.getElementById("resendCodeBtn");
  if (!panel) return;
  panel.classList.toggle("otp-ready", Boolean(show));
  if (otpInput) {
    otpInput.disabled = !show;
    if (!show) otpInput.value = "";
  }
  if (verifyBtn) verifyBtn.disabled = true;
  if (resendBtn) resendBtn.disabled = !show || !lastLoginCredentials;
  if (show) {
    setOtpHint("Code sent. Enter it below (4 to 8 digits).", false);
    otpInput?.focus();
  } else {
    setOtpHint("Go back and request a new verification code.", false);
  }
}

function setOtpHint(text, isError = false) {
  const hint = document.getElementById("otpValidationHint");
  if (!hint) return;
  hint.textContent = text;
  hint.classList.toggle("error", Boolean(isError));
}

function sanitizeOtpInput(raw) {
  return String(raw || "")
    .replace(/\D+/g, "")
    .slice(0, 8);
}

function validateOtpField() {
  const otpInput = document.getElementById("otpCodeInput");
  const verifyBtn = document.getElementById("verifyCodeBtn");
  if (!otpInput) return false;
  if (otpInput.disabled) {
    if (verifyBtn) verifyBtn.disabled = true;
    setOtpHint("Go back and request a new verification code.", false);
    return false;
  }

  otpInput.value = sanitizeOtpInput(otpInput.value);
  const code = otpInput.value.trim();

  if (!code) {
    otpInput.classList.remove("input-invalid");
    setOtpHint("Enter a 4 to 8 digit code.", false);
    if (verifyBtn) verifyBtn.disabled = true;
    return false;
  }

  const valid = OTP_REGEX.test(code);
  otpInput.classList.toggle("input-invalid", !valid);
  setOtpHint(
    valid ? "Code format looks good." : "OTP must be 4 to 8 digits.",
    !valid,
  );
  if (verifyBtn) verifyBtn.disabled = !valid;
  return valid;
}

async function requestOtpCode(credentials, { flow = "login" } = {}) {
  const email = String(credentials?.email || "").trim();
  const password = String(credentials?.password || "");
  if (!email || !password) {
    setMessage("Email and password are required.", "error");
    return;
  }
  persistLoginEmail(email);
  persistOtpCredentials({ email, password });
  setMessage("Sending verification code...", "info");
  const data = await api("/login/request-code", {
    method: "POST",
    auth: false,
    body: { email, password },
  });
  loginChallengeId = String(data.challenge_id || "");
  if (data.debug_code) {
    const verification = await api("/login/verify-code", {
      method: "POST",
      auth: false,
      body: { challenge_id: loginChallengeId, code: data.debug_code },
    });
    clearOtpSession();
    clearOtpCredentials();
    return verification;
  }
  if (loginChallengeId) {
    persistOtpSession({
      challengeId: loginChallengeId,
      email,
      destinationMasked: data.destination_masked,
      flow,
    });
  } else {
    clearOtpSession();
    clearOtpCredentials();
  }
  lastLoginCredentials = { email, password };
  updateOtpPageContext(readOtpSession());
  return data;
}

function finishLogin(token, successMessage = "Login successful. Redirecting...") {
  const accessToken = String(token || "").trim();
  if (!accessToken) {
    throw new Error("No access token returned.");
  }
  localStorage.setItem(TOKEN_KEY, accessToken);
  clearOtpSession();
  clearOtpCredentials();
  loginChallengeId = "";
  lastLoginCredentials = null;
  setMessage(successMessage, "success");
  window.setTimeout(() => {
    resolvePreferredFrontendUrl("location.html")
      .then((target) => {
        window.location.replace(target || "location.html");
      })
      .catch(() => {
        window.location.replace("location.html");
      });
  }, 300);
}

async function verifyOtpCode() {
  const otpInput = document.getElementById("otpCodeInput");
  const code = sanitizeOtpInput(otpInput?.value || "");
  if (!loginChallengeId) {
    setMessage("Request a verification code first.", "error");
    return;
  }
  if (!OTP_REGEX.test(code)) {
    validateOtpField();
    setMessage("OTP format is invalid. Enter 4 to 8 digits.", "error");
    return;
  }

  setMessage("Verifying code...", "info");
  const data = await api("/login/verify-code", {
    method: "POST",
    auth: false,
    body: { challenge_id: loginChallengeId, code },
  });
  finishLogin(data.access_token);
}

function bindLoginPage() {
  const loginForm = document.getElementById("loginForm");
  const submitBtn = loginForm?.querySelector(".redirect-action");
  const token = localStorage.getItem(TOKEN_KEY) || "";
  if (token) {
    setMessage(
      "You are already signed in. Continue to dashboard or location setup.",
      "success",
    );
  }
  restoreLoginEmail();

  loginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setSubmitBusy(submitBtn, true, "Signing in...", "Continue");
    const fd = new FormData(loginForm);
    const credentials = {
      email: String(fd.get("email") || "").trim(),
      password: String(fd.get("password") || ""),
    };
    if (!credentials.email || !credentials.password) {
      setSubmitBusy(submitBtn, false, "Signing in...", "Continue");
      setMessage("Email and password are required.", "error");
      return;
    }
    try {
      persistLoginEmail(credentials.email);
      const data = await api("/login", {
        method: "POST",
        auth: false,
        body: credentials,
      });
      finishLogin(data.access_token, "Sign-in successful. Redirecting...");
    } catch (err) {
      if (!isOtpRequiredError(err)) {
        setSubmitBusy(submitBtn, false, "Signing in...", "Continue");
        setMessage(err.message, "error");
        return;
      }
      try {
        const data = await requestOtpCode(credentials, { flow: "login" });
        if (data?.access_token) {
          finishLogin(data.access_token, "Sign-in successful. Redirecting...");
          return;
        }
        setMessage(data.message || "Verification code sent. Redirecting...", "success");
        window.setTimeout(() => {
          resolvePreferredFrontendUrl(buildOtpPageUrl("login"))
            .then((target) => {
              window.location.replace(target || buildOtpPageUrl("login"));
            })
            .catch(() => {
              window.location.replace(buildOtpPageUrl("login"));
            });
        }, 200);
      } catch (otpErr) {
        setSubmitBusy(submitBtn, false, "Signing in...", "Continue");
        setMessage(otpErr.message, "error");
      }
    }
  });
}

function bindOtpPage() {
  const verifyBtn = document.getElementById("verifyCodeBtn");
  const resendBtn = document.getElementById("resendCodeBtn");
  const otpInput = document.getElementById("otpCodeInput");
  const session = readOtpSession();

  updateOtpPageContext(session);
  if (!session) {
    loginChallengeId = "";
    lastLoginCredentials = readOtpCredentials();
    showOtpPanel(false);
    setMessage("Start from sign in or sign up to receive a verification code.", "error");
    if (resendBtn) resendBtn.disabled = true;
    return;
  }

  loginChallengeId = session.challengeId;
  lastLoginCredentials = readOtpCredentials();
  showOtpPanel(true);
  validateOtpField();
  setMessage("Enter the verification code to continue.", "info");
  if (resendBtn) resendBtn.disabled = !lastLoginCredentials;

  verifyBtn?.addEventListener("click", async () => {
    setSubmitBusy(verifyBtn, true, "Verifying...", "Verify Code");
    try {
      await verifyOtpCode();
    } catch (err) {
      setSubmitBusy(verifyBtn, false, "Verifying...", "Verify Code");
      setMessage(err.message, "error");
    }
  });

  resendBtn?.addEventListener("click", async () => {
    const credentials = readOtpCredentials();
    if (!credentials) {
      setMessage("For security, go back and request a new code.", "error");
      if (resendBtn) resendBtn.disabled = true;
      return;
    }
    try {
      const data = await requestOtpCode(credentials, { flow: session.flow });
      showOtpPanel(true);
      validateOtpField();
      setMessage(data.message || "A new verification code was sent.", "success");
    } catch (err) {
      setMessage(err.message, "error");
    }
  });

  otpInput?.addEventListener("input", () => {
    validateOtpField();
  });

  otpInput?.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (!validateOtpField()) return;
    setSubmitBusy(verifyBtn, true, "Verifying...", "Verify Code");
    try {
      await verifyOtpCode();
    } catch (err) {
      setSubmitBusy(verifyBtn, false, "Verifying...", "Verify Code");
      setMessage(err.message, "error");
    }
  });
}

function bindSignupPage() {
  const registerForm = document.getElementById("registerForm");
  const submitBtn = registerForm?.querySelector(".redirect-action");
  registerForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setSubmitBusy(submitBtn, true, "Creating account...", "Create account");
    const fd = new FormData(registerForm);
    const payload = {
      full_name: String(fd.get("full_name") || "").trim(),
      email: String(fd.get("email") || "").trim(),
      password: String(fd.get("password") || ""),
      confirm_password: String(fd.get("confirm_password") || ""),
    };
    const validationError = validateSignupPayload(payload);
    if (validationError) {
      setSubmitBusy(submitBtn, false, "Creating account...", "Create account");
      setMessage(validationError, "error");
      return;
    }
    try {
      setMessage("Creating account...", "info");
      const registration = await api("/register", {
        method: "POST",
        auth: false,
        body: {
          full_name: payload.full_name,
          email: payload.email,
          password: payload.password,
        },
      });
      localStorage.removeItem(TOKEN_KEY);
      if (registration.access_token) {
        finishLogin(registration.access_token, "Account created. Redirecting...");
        return;
      }
      if (registration.otp_required === false) {
        setMessage(registration.message || "Account created. Sign in to continue.", "success");
        window.setTimeout(() => {
          window.location.href = "login.html";
        }, 250);
        return;
      }
      const data = await requestOtpCode(
        {
          email: payload.email,
          password: payload.password,
        },
        { flow: "signup" },
      );
      if (data?.access_token) {
        finishLogin(data.access_token, "Account created. Redirecting...");
        return;
      }
      setMessage(data.message || "Account created. Redirecting to verification...", "success");
      window.setTimeout(() => {
        resolvePreferredFrontendUrl(buildOtpPageUrl("signup"))
          .then((target) => {
            window.location.replace(target || buildOtpPageUrl("signup"));
          })
          .catch(() => {
            window.location.replace(buildOtpPageUrl("signup"));
          });
        }, 200);
    } catch (err) {
      setSubmitBusy(submitBtn, false, "Creating account...", "Create account");
      setMessage(err.message, "error");
    }
  });
}

async function resolveRememberedSessionTarget() {
  const token = localStorage.getItem(TOKEN_KEY) || "";
  if (!token) return null;
  try {
    const locationState = await api("/users/me/location", {
      method: "GET",
      auth: true,
    });
    if (locationState && locationState.location_permission_granted) {
      return "dashboard.html";
    }
    return "location.html";
  } catch (err) {
    const status = Number(err?.status || 0);
    if (status === 401 || status === 403) {
      localStorage.removeItem(TOKEN_KEY);
    }
    return null;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const page = String(document.body?.dataset?.page || "").toLowerCase();
  setupNavToggle();
  bindPasswordToggles();
  bindRedirectLinks();
  const changeApiBaseBtn = document.getElementById("apiBaseChangeBtn");
  changeApiBaseBtn?.addEventListener("click", async () => {
    await promptForApiBaseChange();
  });
  (async () => {
    try {
      await bootstrapApiBase();
      updateApiBaseHintLabel();
      if (page === "login") bindLoginPage();
      if (page === "signup") bindSignupPage();
      if (page === "otp") bindOtpPage();
      if (shouldAutoSwitchToBackendHostedPage()) {
        const backendReady = await isBackendReachable();
        if (backendReady) {
          const target = backendHostedAuthUrl(page);
          if (!window.location.href.startsWith(target)) {
            window.location.replace(target);
            return;
          }
        }
      }
      const rememberedTarget = await resolveRememberedSessionTarget();
      if (rememberedTarget && (page === "login" || page === "signup" || page === "otp")) {
        window.location.replace(
          (await resolvePreferredFrontendUrl(rememberedTarget)) || rememberedTarget,
        );
        return;
      }
      const pendingOtpSession = readOtpSession();
      if (pendingOtpSession && (page === "login" || page === "signup")) {
        const otpTarget = buildOtpPageUrl(pendingOtpSession.flow);
        window.location.replace((await resolvePreferredFrontendUrl(otpTarget)) || otpTarget);
      }
    } catch (err) {
      setMessage(
        err?.message || "Sign-in is available, but automatic page checks failed.",
        "error",
      );
    }
  })();
});
