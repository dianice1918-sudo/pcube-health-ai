const TOKEN_KEY = "pcube_access_token";
const API_BASE_KEY = "pcube_api_base";
const API_KEY_STORAGE = "pcube_api_key";
const SAME_ORIGIN_API_KEY = "pcube_same_origin_api";
const OTP_REQUIRED_ERROR_FRAGMENT = "OTP verification required";
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

function isApiServedFrontend() {
  const path = String(window.location.pathname || "");
  return path.startsWith("/frontend/") || path.startsWith("/app/");
}

function devApiFallbackBase() {
  return `http://127.0.0.1:${DEFAULT_API_PORT}`;
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
  if (explicit === "1") return true;
  if (explicit === "0") return false;
  if (window.location.protocol === "file:") return false;
  return isDevPort(window.location.port) && isApiServedFrontend();
}

function ensureApiBaseDefault() {
  if (isLocalStaticDevPage()) {
    localStorage.setItem(API_BASE_KEY, devApiFallbackBase());
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
    localStorage.setItem(API_BASE_KEY, devApiFallbackBase());
    return;
  }
  if (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") {
    if (window.location.port === "5500" || window.location.port === "5501" || window.location.port === "5502") {
      localStorage.setItem(API_BASE_KEY, devApiFallbackBase());
      return;
    }
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
      return devApiFallbackBase();
    }
    return normalized;
  }
  if (configured) {
    localStorage.removeItem(API_BASE_KEY);
  }
  if (window.location.protocol === "file:") return devApiFallbackBase();
  if (isLocalStaticDevPage()) return devApiFallbackBase();
  return "";
}

// Initialize keyboard navigation (roving tabindex) for services grid
function initServicesGridKeyboardNav() {
  const grid = document.getElementById("servicesGrid");
  if (!grid) return;
  const items = Array.from(grid.querySelectorAll(".service-card"));
  if (!items.length) return;

  // set initial tabindex: first item 0, others -1
  items.forEach((it, i) => {
    it.setAttribute("tabindex", i === 0 ? "0" : "-1");
    it.dataset.index = String(i);
  });

  function focusAt(index) {
    const idx = Math.max(0, Math.min(items.length - 1, index));
    items.forEach((it, i) => it.setAttribute("tabindex", i === idx ? "0" : "-1"));
    const el = items[idx];
    if (el && typeof el.focus === "function") el.focus();
  }

  function onKeyDown(e) {
    const el = e.currentTarget;
    const idx = Number(el.dataset.index || 0);
    let targetIndex = null;
    switch (e.key) {
      case "ArrowRight":
      case "ArrowDown":
        targetIndex = idx + 1;
        break;
      case "ArrowLeft":
      case "ArrowUp":
        targetIndex = idx - 1;
        break;
      case "Home":
        targetIndex = 0;
        break;
      case "End":
        targetIndex = items.length - 1;
        break;
      case "Enter":
      case " ":
      case "Spacebar":
        // activate
        e.preventDefault();
        el.click();
        return;
      default:
        return;
    }
    if (targetIndex !== null) {
      e.preventDefault();
      if (targetIndex < 0) targetIndex = 0;
      if (targetIndex >= items.length) targetIndex = items.length - 1;
      focusAt(targetIndex);
    }
  }

  items.forEach((it) => {
    it.addEventListener("keydown", onKeyDown);
    // ensure click also sets tabindex to clicked item
    it.addEventListener("click", () => {
      const i = Number(it.dataset.index || 0);
      items.forEach((el, idx) => el.setAttribute("tabindex", idx === i ? "0" : "-1"));
    });
  });
}

// call init once DOM handlers are set up
window.setTimeout(initServicesGridKeyboardNav, 50);

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

// Ensure a sensible default is present so sections start the backend immediately
ensureApiBaseDefault();
let API_BASE = resolveApiBase();

function toApiUrl(path) {
  const normalized = String(path || "").startsWith("/")
    ? String(path)
    : `/${String(path || "")}`;
  return API_BASE ? `${API_BASE}${normalized}` : normalized;
}

const authStateEl = document.getElementById("authState");
const registerForm = document.getElementById("registerForm");
const loginForm = document.getElementById("loginForm");
const healthForm = document.getElementById("healthForm");
const stepSyncForm = document.getElementById("stepSyncForm");
const chatForm = document.getElementById("chatForm");
const chatImageForm = document.getElementById("chatImageForm");
const wearableConnectForm = document.getElementById("wearableConnectForm");
const wearableSyncForm = document.getElementById("wearableSyncForm");
const pushTokenForm = document.getElementById("pushTokenForm");
const shareForm = document.getElementById("shareForm");

const locationOut = document.getElementById("locationOut");
const stepOut = document.getElementById("stepOut");
const healthOut = document.getElementById("healthOut");
const intelOut = document.getElementById("intelOut");
const chatOut = document.getElementById("chatOut");
const chatThread = document.getElementById("chatThread");
const chatVoiceBtn = document.getElementById("chatVoiceBtn");
const chatSpeakToggleBtn = document.getElementById("chatSpeakToggleBtn");
const chatTextInput = chatForm?.querySelector('textarea[name="question"]');
const insightOut = document.getElementById("insightOut");
const trendGraph = document.getElementById("trendGraph");
const wearableOut = document.getElementById("wearableOut");
const pushOut = document.getElementById("pushOut");
const shareOut = document.getElementById("shareOut");
const shareHint = document.getElementById("shareHint");
const stepSensorStatus = document.getElementById("stepSensorStatus");
const dashboardWindowSelect = document.getElementById("dashboardWindowSelect");
const refreshDashboardAllBtn = document.getElementById(
  "refreshDashboardAllBtn",
);
const toggleAutoRefreshBtn = document.getElementById("toggleAutoRefreshBtn");
const toggleFocusModeBtn = document.getElementById("toggleFocusModeBtn");
const dashboardStatus = document.getElementById("dashboardStatus");
const dashboardEntryHint = document.getElementById("dashboardEntryHint");
const dashboardChart = document.getElementById("dashboardChart");
const chartTabButtons = Array.from(document.querySelectorAll(".chart-tab"));
const notificationFilterButtons = Array.from(
  document.querySelectorAll(".notif-filter"),
);
const modePillButtons = Array.from(document.querySelectorAll(".mode-pill"));
const sectionNavLinks = Array.from(
  document.querySelectorAll('.top-nav .nav-item[href*="#"]'),
);
const openMobileGuideBtn = document.getElementById("openMobileGuideBtn");
const opsWorkspace = document.getElementById("opsWorkspace");
const enterDashboardBtn = document.getElementById("enterDashboardBtn");
const openWorkspaceTourBtn = document.getElementById("openWorkspaceTourBtn");
const openFreeToolsBtn = document.getElementById("openFreeToolsBtn");
const openProToolsBtn = document.getElementById("openProToolsBtn");
const welcomeTitle = document.getElementById("welcomeTitle");
const welcomeSubtitle = document.getElementById("welcomeSubtitle");

function getFirebasePushBridge() {
  const bridge = window.PCubeFirebasePush;
  if (!bridge || typeof bridge.getBrowserPushToken !== "function") return null;
  return bridge;
}

const heroRiskMini = document.getElementById("heroRiskMini");
const heroForecastMini = document.getElementById("heroForecastMini");
const heroUnreadMini = document.getElementById("heroUnreadMini");

const dailyPlanMeta = document.getElementById("dailyPlanMeta");
const dailyPlanList = document.getElementById("dailyPlanList");
const notificationList = document.getElementById("notificationList");

const kpiRiskValue = document.getElementById("kpiRiskValue");
const kpiForecastValue = document.getElementById("kpiForecastValue");
const kpiTrendValue = document.getElementById("kpiTrendValue");
const kpiStreakValue = document.getElementById("kpiStreakValue");
const kpiWeeklyScoreValue = document.getElementById("kpiWeeklyScoreValue");
const kpiUnreadValue = document.getElementById("kpiUnreadValue");
const kpiRiskBar = document.getElementById("kpiRiskBar");

const listWearablesBtn = document.getElementById("listWearablesBtn");
const listPushTokensBtn = document.getElementById("listPushTokensBtn");
const testPushBtn = document.getElementById("testPushBtn");
const loadDailyPlanBtn = document.getElementById("loadDailyPlanBtn");
const loadNotificationsBtn = document.getElementById("loadNotificationsBtn");
const oauthGoogleBtn = document.getElementById("oauthGoogleBtn");
const oauthFitbitBtn = document.getElementById("oauthFitbitBtn");
const loadDashboardBtnHero = document.getElementById("loadDashboardBtnHero");
const logoutBtn = document.getElementById("logoutBtn");
const startMotionStepBtn = document.getElementById("startMotionStepBtn");
const stopMotionStepBtn = document.getElementById("stopMotionStepBtn");
const resetMotionStepBtn = document.getElementById("resetMotionStepBtn");
const motionStepStatus = document.getElementById("motionStepStatus");
const userMenuBtn = document.getElementById("userMenuBtn");
const userMenuPanel = document.getElementById("userMenuPanel");

const tourModal = document.getElementById("tourModal");
const tourCloseBtn = document.getElementById("tourCloseBtn");

const stepSyncState = {
  packetsSent: 0,
  lastSyncAt: null,
  lastMode: "none",
  lastSensorType: "-",
  lastAcceptedDelta: 0,
  lastTotalSteps: 0,
};

const motionStepState = {
  enabled: false,
  date: "",
  todayCount: 0,
  pendingDelta: 0,
  lastMotionAt: 0,
  lastMagnitude: null,
  flushTimer: null,
};

const dashboardState = {
  chart: "risk",
  windowDays: Number(dashboardWindowSelect?.value || 30),
  autoRefresh: false,
  autoRefreshTimer: null,
  focusMode: false,
  workspaceOpen: Boolean(opsWorkspace && !opsWorkspace.classList.contains("hidden")),
  notificationFilter: "ALL",
  riskHistory: [],
  healthHistory: [],
  currentDashboard: null,
  summaryLoaded: false,
};

const SECTION_PAGE_MAP = {
  interactiveDashboard: "dashboard.html",
  alertHub: "dashboard-alert-hub.html",
  integrationsHub: "dashboard-integrations.html",
  stepCounterHub: "dashboard-integrations.html",
};
const PAGE_ASSET_VERSION = "20260323e";

function withPageVersion(target) {
  const raw = String(target || "").trim();
  if (!raw) return raw;
  if (/^(https?:|mailto:|tel:|#)/i.test(raw)) return raw;

  const hashIndex = raw.indexOf("#");
  const hashPart = hashIndex >= 0 ? raw.slice(hashIndex) : "";
  const base = hashIndex >= 0 ? raw.slice(0, hashIndex) : raw;

  if (!/\.html(\?|$)/i.test(base)) return raw;
  if (/[?&]v=/.test(base)) return raw;

  const separator = base.includes("?") ? "&" : "?";
  return `${base}${separator}v=${PAGE_ASSET_VERSION}${hashPart}`;
}

const chatUiState = {
  ttsEnabled: localStorage.getItem("pcube_tts_enabled") === "1",
  listening: false,
  recognition: null,
};
let lastIntelSpeechKey = "";

function setAuthState() {
  if (!authStateEl) return;
  authStateEl.textContent = authToken ? "Authenticated" : "Not signed in";
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

function todayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function coerceNumber(v) {
  if (v === null || v === undefined || v === "") return undefined;
  const n = Number(v);
  return Number.isNaN(n) ? undefined : n;
}

function pretty(data) {
  return JSON.stringify(data, null, 2);
}

function setDashboardStatus(msg) {
  if (dashboardStatus) dashboardStatus.textContent = msg;
}

function dashboardHasUserEntries(dashboard = dashboardState.currentDashboard) {
  const risk = dashboard?.risk_summary || {};
  const forecast = dashboard?.forecast || {};
  const healthCount = Array.isArray(dashboardState.healthHistory)
    ? dashboardState.healthHistory.length
    : 0;
  const riskCount = Array.isArray(dashboardState.riskHistory)
    ? dashboardState.riskHistory.length
    : 0;
  return (
    healthCount > 0 ||
    riskCount > 0 ||
    risk.current_risk != null ||
    forecast.next_risk_prediction != null
  );
}

function renderDashboardEntryHint(dashboard = dashboardState.currentDashboard) {
  if (!dashboardEntryHint) return;
  if (!dashboardState.summaryLoaded) {
    dashboardEntryHint.textContent =
      "Your dashboard updates from your own records, sensors, and connected tools. Add your first health entry below to personalize it.";
    return;
  }
  if (!dashboardHasUserEntries(dashboard)) {
    dashboardEntryHint.textContent =
      "No personal health entries yet. Add your first health record, sync steps, or connect a wearable to activate the dashboard sections.";
    return;
  }
  dashboardEntryHint.textContent =
    "Dashboard sections are now syncing from your latest entries. Add a new record anytime to refresh your insights.";
}

function formatTrendLabel(rawTrend) {
  const value = String(rawTrend || "UNKNOWN")
    .trim()
    .toUpperCase();
  if (value === "INSUFFICIENT_DATA") return "Insufficient";
  const pretty = value.replace(/_/g, " ").toLowerCase();
  return pretty.charAt(0).toUpperCase() + pretty.slice(1);
}

function renderWelcomeGreeting() {
  const now = new Date();
  const hour = now.getHours();
  const greeting =
    hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const dateLabel = now.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
  if (welcomeTitle)
    welcomeTitle.textContent = `${greeting}. Welcome to P-Cube Health AI.`;
  if (welcomeSubtitle) {
    welcomeSubtitle.textContent = `Today is ${dateLabel}. Select free or pro services, then open the live dashboard when needed.`;
  }
}

async function ensureWorkspaceOpen({ load = true, scrollToId } = {}) {
  if (opsWorkspace && !dashboardState.workspaceOpen) {
    opsWorkspace.classList.remove("hidden");
    dashboardState.workspaceOpen = true;
    setDashboardStatus("Workspace ready. Syncing your latest entries...");
  }
  renderDashboardEntryHint();
  if (load) await loadDashboardInteractive();
  if (scrollToId) {
    const target = document.getElementById(scrollToId);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function openSectionById(sectionId) {
  const target = document.getElementById(sectionId);
  if (target) {
    // ensure API base is set when navigating to a new section
    ensureApiBaseDefault();
    await ensureWorkspaceOpen({ load: true, scrollToId: sectionId });
    return;
  }
  const page = SECTION_PAGE_MAP[String(sectionId || "")];
  if (page) {
    window.location.href = withPageVersion(`${page}#${sectionId}`);
  }
}

function getSectionIdFromHref(rawHref) {
  const href = String(rawHref || "").trim();
  if (!href) return "";
  const hashIndex = href.indexOf("#");
  if (hashIndex < 0) return "";
  return href.slice(hashIndex + 1).trim();
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

function renderSensorStatus() {
  if (!stepSensorStatus) return;
  const lastSync = stepSyncState.lastSyncAt
    ? formatDateTimeLocal(stepSyncState.lastSyncAt.toISOString())
    : "N/A";
  stepSensorStatus.textContent = `Packets: ${stepSyncState.packetsSent} | Mode: ${stepSyncState.lastMode} | Sensor: ${stepSyncState.lastSensorType} | Accepted delta: ${stepSyncState.lastAcceptedDelta} | Total steps: ${stepSyncState.lastTotalSteps} | Last sync: ${lastSync}`;
}

function loadMotionCounterState() {
  motionStepState.date = todayISO();
  motionStepState.todayCount = 0;
  motionStepState.pendingDelta = 0;
  try {
    const raw = localStorage.getItem("pcube_motion_counter");
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return;
    const storedDate = String(parsed.date || "");
    if (storedDate !== motionStepState.date) return;
    motionStepState.todayCount = Number(parsed.today_count || 0);
    motionStepState.pendingDelta = Number(parsed.pending_delta || 0);
  } catch {
    // Ignore malformed local cache
  }
}

function persistMotionCounterState() {
  localStorage.setItem(
    "pcube_motion_counter",
    JSON.stringify({
      date: motionStepState.date,
      today_count: motionStepState.todayCount,
      pending_delta: motionStepState.pendingDelta,
    }),
  );
}

function renderMotionStepStatus(extra) {
  if (!motionStepStatus) return;
  const mode = motionStepState.enabled ? "ON" : "OFF";
  const suffix = extra ? ` | ${extra}` : "";
  motionStepStatus.textContent = `Motion Counter: ${mode} | Date: ${motionStepState.date} | Today: ${motionStepState.todayCount}${suffix}`;
}

function resetMotionCounterIfNewDay(force = false) {
  const today = todayISO();
  if (force || motionStepState.date !== today) {
    motionStepState.date = today;
    motionStepState.todayCount = 0;
    motionStepState.pendingDelta = 0;
    motionStepState.lastMagnitude = null;
    persistMotionCounterState();
    renderMotionStepStatus("Daily reset to 0");
  }
}

async function flushMotionStepSync() {
  if (!authToken) return;
  if (motionStepState.pendingDelta <= 0) return;
  const delta = motionStepState.pendingDelta;
  motionStepState.pendingDelta = 0;
  persistMotionCounterState();
  try {
    const body = {
      device_id: "web-motion-primary",
      sensor_type: "ACCELEROMETER",
      detected_steps_delta: Math.max(0, Math.trunc(delta)),
      activity_minutes_delta: 0,
      record_date: motionStepState.date,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    };
    const result = await api("/device/steps/sync", { method: "POST", body });
    stepSyncState.packetsSent += 1;
    stepSyncState.lastSyncAt = new Date();
    stepSyncState.lastMode = String(result.processing_mode || "-");
    stepSyncState.lastSensorType = String(
      result.sensor_type || "ACCELEROMETER",
    );
    stepSyncState.lastAcceptedDelta = Number(result.accepted_step_delta || 0);
    stepSyncState.lastTotalSteps = Number(result.total_steps || 0);
    renderSensorStatus();
    if (stepOut) stepOut.textContent = pretty(result);
    renderMotionStepStatus(`Synced +${Math.max(0, Math.trunc(delta))}`);
  } catch (e) {
    motionStepState.pendingDelta += delta;
    persistMotionCounterState();
    renderMotionStepStatus("Sync pending");
    if (stepOut) stepOut.textContent = e.message;
  }
}

function scheduleMotionFlush() {
  if (motionStepState.flushTimer) return;
  motionStepState.flushTimer = window.setTimeout(async () => {
    motionStepState.flushTimer = null;
    await flushMotionStepSync();
  }, 1400);
}

function handleMotionEvent(event) {
  if (!motionStepState.enabled) return;
  resetMotionCounterIfNewDay(false);
  const now = Date.now();
  if (now - motionStepState.lastMotionAt < 350) return;
  const ax = event?.acceleration?.x;
  const ay = event?.acceleration?.y;
  const az = event?.acceleration?.z;
  const hasLinear = [ax, ay, az].some((v) => typeof v === "number");
  const gx = hasLinear ? ax : event?.accelerationIncludingGravity?.x;
  const gy = hasLinear ? ay : event?.accelerationIncludingGravity?.y;
  const gz = hasLinear ? az : event?.accelerationIncludingGravity?.z;
  if (![gx, gy, gz].some((v) => typeof v === "number")) return;
  const magnitude = Math.sqrt(
    (Number(gx) || 0) ** 2 + (Number(gy) || 0) ** 2 + (Number(gz) || 0) ** 2,
  );
  if (motionStepState.lastMagnitude == null) {
    motionStepState.lastMagnitude = magnitude;
    return;
  }
  const deltaMagnitude = Math.abs(magnitude - motionStepState.lastMagnitude);
  motionStepState.lastMagnitude = magnitude;
  const threshold = hasLinear ? 0.85 : 1.15;
  if (deltaMagnitude < threshold) return;
  motionStepState.lastMotionAt = now;
  motionStepState.todayCount += 1;
  motionStepState.pendingDelta += 1;
  persistMotionCounterState();
  renderMotionStepStatus("+1 detected");
  scheduleMotionFlush();
}

async function startMotionCounter() {
  if (!authToken) {
    renderMotionStepStatus("Login required");
    return;
  }
  if (typeof window === "undefined" || !("DeviceMotionEvent" in window)) {
    renderMotionStepStatus("Device motion not supported");
    return;
  }
  try {
    const requestPermission = window.DeviceMotionEvent?.requestPermission;
    if (typeof requestPermission === "function") {
      const permission = await requestPermission.call(window.DeviceMotionEvent);
      if (permission !== "granted") {
        renderMotionStepStatus("Motion permission denied");
        return;
      }
    }
    resetMotionCounterIfNewDay(false);
    window.addEventListener("devicemotion", handleMotionEvent, {
      passive: true,
    });
    motionStepState.enabled = true;
    localStorage.setItem("pcube_motion_counter_enabled", "1");
    renderMotionStepStatus("Listening for motion");
  } catch (e) {
    renderMotionStepStatus("Motion start failed");
    if (stepOut) stepOut.textContent = e.message;
  }
}

function stopMotionCounter() {
  motionStepState.enabled = false;
  window.removeEventListener("devicemotion", handleMotionEvent);
  localStorage.setItem("pcube_motion_counter_enabled", "0");
  renderMotionStepStatus("Stopped");
}

async function resetMotionCounterToday() {
  resetMotionCounterIfNewDay(true);
  await flushMotionStepSync();
}

function toBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () =>
      reject(reader.error || new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}

function setChatSpeakToggleLabel() {
  if (!chatSpeakToggleBtn) return;
  chatSpeakToggleBtn.textContent = `Read Aloud: ${chatUiState.ttsEnabled ? "On" : "Off"}`;
}

function setChatVoiceButtonLabel() {
  if (!chatVoiceBtn) return;
  chatVoiceBtn.textContent = chatUiState.listening
    ? "Listening..."
    : "Use Voice";
}

function escapeChatHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatChatInline(text) {
  let html = escapeChatHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  return html;
}

function renderChatBlock(block) {
  const lines = String(block || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return "";

  if (lines.every((line) => /^\d+\.\s+/.test(line))) {
    return `<ol class="chat-rich-list">${lines
      .map((line) => `<li>${formatChatInline(line.replace(/^\d+\.\s+/, ""))}</li>`)
      .join("")}</ol>`;
  }

  if (lines.every((line) => /^-\s+/.test(line))) {
    return `<ul class="chat-rich-list">${lines
      .map((line) => `<li>${formatChatInline(line.replace(/^-\s+/, ""))}</li>`)
      .join("")}</ul>`;
  }

  return lines
    .map((line) => {
      const headingMatch = line.match(/^#{1,6}\s+(.*)$/);
      if (headingMatch) {
        return `<div class="chat-rich-heading">${formatChatInline(
          headingMatch[1],
        )}</div>`;
      }
      return `<p class="chat-rich-paragraph">${formatChatInline(line)}</p>`;
    })
    .join("");
}

function renderRichChatMessage(text) {
  const normalized = String(text || "").replace(/\r\n?/g, "\n").trim();
  if (!normalized) return "";
  return normalized
    .split(/\n{2,}/)
    .map((block) => renderChatBlock(block))
    .filter(Boolean)
    .join("");
}

function normalizeChatSpeech(text) {
  return String(text || "")
    .replace(/\r\n?/g, "\n")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/\n{2,}/g, "\n")
    .trim();
}

function appendChatBubble(role, text, extraClass = "") {
  if (!chatThread) return null;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}${extraClass ? ` ${extraClass}` : ""}`;
  const rawText = String(text || "");
  if (role === "bot" && extraClass !== "typing") {
    const content = document.createElement("div");
    content.className = "chat-bubble-content";
    const richHtml = renderRichChatMessage(rawText);
    if (richHtml) {
      content.innerHTML = richHtml;
      bubble.appendChild(content);
    } else {
      bubble.textContent = rawText;
    }
  } else {
    bubble.textContent = rawText;
  }
  chatThread.appendChild(bubble);
  bubble.scrollIntoView({ behavior: "smooth", block: "end" });
  return bubble;
}

function speakChatText(text) {
  if (!chatUiState.ttsEnabled) return;
  if (!("speechSynthesis" in window)) return;
  const msg = normalizeChatSpeech(text);
  if (!msg) return;
  const utter = new SpeechSynthesisUtterance(msg.slice(0, 1800));
  utter.rate = 0.98;
  utter.pitch = 1;
  utter.volume = 1;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}

function applyIntelVisualState(level) {
  if (!document?.body) return;
  const normalized = String(level || "NORMAL").toUpperCase();
  document.body.dataset.intelLevel = normalized;
}

function speakLiveIntel(intel) {
  if (!chatUiState.ttsEnabled) return;
  if (!("speechSynthesis" in window)) return;
  const level = String(intel?.alert_level || "NORMAL").toUpperCase();
  if (!["WARNING", "URGENT"].includes(level)) return;
  const msg = String(intel?.speak_text || intel?.summary || "").trim();
  if (!msg) return;
  const speechKey = `${level}|${msg}`;
  if (speechKey === lastIntelSpeechKey) return;
  lastIntelSpeechKey = speechKey;
  const utter = new SpeechSynthesisUtterance(msg.slice(0, 1800));
  utter.rate = 0.96;
  utter.pitch = 1;
  utter.volume = 1;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}

function initSpeechRecognition() {
  if (chatUiState.recognition) return chatUiState.recognition;
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = "en-US";
  rec.interimResults = false;
  rec.continuous = false;
  rec.maxAlternatives = 1;

  rec.onstart = () => {
    chatUiState.listening = true;
    setChatVoiceButtonLabel();
  };
  rec.onend = () => {
    chatUiState.listening = false;
    setChatVoiceButtonLabel();
  };
  rec.onerror = (event) => {
    chatUiState.listening = false;
    setChatVoiceButtonLabel();
    if (chatOut)
      chatOut.textContent = `Voice input failed: ${event.error || "unknown error"}`;
  };
  rec.onresult = (event) => {
    const transcript = String(
      event?.results?.[0]?.[0]?.transcript || "",
    ).trim();
    if (!transcript) return;
    if (chatTextInput) {
      chatTextInput.value = chatTextInput.value
        ? `${chatTextInput.value} ${transcript}`
        : transcript;
      chatTextInput.focus();
    }
  };

  chatUiState.recognition = rec;
  return rec;
}

function showTour(force = false) {
  if (!tourModal) return;
  const seen = localStorage.getItem("pcube_tour_seen") === "1";
  if (!seen || force) tourModal.classList.remove("hidden");
}

function hideTour() {
  if (!tourModal) return;
  tourModal.classList.add("hidden");
  localStorage.setItem("pcube_tour_seen", "1");
}

async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && authToken) headers["Authorization"] = `Bearer ${authToken}`;
  const apiKey = String(localStorage.getItem(API_KEY_STORAGE) || "").trim();
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
      authToken = "";
      localStorage.removeItem(TOKEN_KEY);
      setAuthState();
      window.location.replace("login.html");
      throw new Error("Session expired. Please login again.");
    }
    const detail =
      typeof payload === "string" ? payload : payload.detail || pretty(payload);
    throw new Error(`${res.status}: ${detail}`);
  }
  return payload;
}

function setRiskMeter(scoreRaw) {
  if (!kpiRiskBar) return;
  const score = Number(scoreRaw);
  const safe = Number.isNaN(score) ? 0 : Math.max(0, Math.min(1, score));
  kpiRiskBar.style.width = `${safe * 100}%`;
}

function renderKPIs(dashboard) {
  const risk = dashboard?.risk_summary || {};
  const engagement = dashboard?.engagement || {};
  const forecast = dashboard?.forecast || {};
  const trends = dashboard?.trends || {};
  const hasEntries = dashboardHasUserEntries(dashboard);

  if (kpiRiskValue)
    kpiRiskValue.textContent =
      risk.current_risk == null
        ? "--"
        : `${Number(risk.current_risk).toFixed(2)}`;
  if (kpiForecastValue)
    kpiForecastValue.textContent =
      forecast.next_risk_prediction == null
        ? "--"
        : `${Number(forecast.next_risk_prediction).toFixed(2)}`;
  if (kpiTrendValue)
    kpiTrendValue.textContent = hasEntries ? formatTrendLabel(trends.trend) : "--";
  if (kpiStreakValue)
    kpiStreakValue.textContent = hasEntries
      ? `${Number(engagement.current_streak_days || 0)}d`
      : "--";
  if (kpiWeeklyScoreValue)
    kpiWeeklyScoreValue.textContent = hasEntries
      ? `${Number(engagement.weekly_score || 0)}/100`
      : "--";
  if (kpiUnreadValue)
    kpiUnreadValue.textContent = String(
      Number(dashboard?.unread_notifications || 0),
    );
  if (heroRiskMini)
    heroRiskMini.textContent =
      risk.current_risk == null ? "--" : Number(risk.current_risk).toFixed(2);
  if (heroForecastMini) {
    heroForecastMini.textContent =
      forecast.next_risk_prediction == null
        ? "--"
        : Number(forecast.next_risk_prediction).toFixed(2);
  }
  if (heroUnreadMini)
    heroUnreadMini.textContent = String(
      Number(dashboard?.unread_notifications || 0),
    );
  setRiskMeter(risk.current_risk);
}

function renderDailyPlan(plan) {
  if (!dailyPlanList || !dailyPlanMeta) return;
  const completion = Math.round((plan.completion_ratio || 0) * 100);
  dailyPlanMeta.innerHTML = `
    <div class="plan-head">
      <strong>${plan.plan_date}</strong>
      <span class="plan-pill">${completion}% completed</span>
    </div>
    <div class="plan-progress"><span style="width:${completion}%"></span></div>
  `;
  dailyPlanList.innerHTML = "";
  const iconByTask = {
    hydrate_goal: "H",
    step_goal: "S",
    mindful_break: "M",
  };
  for (const task of plan.tasks || []) {
    const wrapper = document.createElement("div");
    wrapper.className = `task-item${task.completed ? " done" : ""}`;
    const icon = iconByTask[task.key] || "T";
    wrapper.innerHTML = `
      <div class="task-top">
        <div class="task-badge">${icon}</div>
        <div>
          <strong>${task.title}</strong>
          <div class="task-meta">${task.description}</div>
          <div class="task-target">${task.target}</div>
        </div>
      </div>
      <div class="task-actions">
        <button class="button ${task.completed ? "ghost" : ""}" data-action="toggle">${task.completed ? "Completed" : "Mark Complete"}</button>
      </div>
    `;
    const toggleBtn = wrapper.querySelector('[data-action="toggle"]');
    if (toggleBtn) {
      toggleBtn.addEventListener("click", async () => {
        const nextState = !task.completed;
        try {
          const updated = await api(`/users/me/daily-plan/${task.key}`, {
            method: "PATCH",
            body: { completed: nextState },
          });
          renderDailyPlan(updated);
          await loadDashboard();
        } catch (e) {
          if (insightOut) insightOut.textContent = e.message;
        }
      });
    }
    dailyPlanList.appendChild(wrapper);
  }
}

function renderNotifications(items) {
  if (!notificationList) return;
  notificationList.innerHTML = "";
  if (!items || !items.length) {
    notificationList.innerHTML = "<p class='note'>No notifications yet.</p>";
    return;
  }
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "notice-item";
    const createdAtLocal = formatDateTimeLocal(item.created_at);
    row.innerHTML = `
      <strong>[${item.severity}] ${item.title}</strong>
      <div class="notice-meta">${item.message}</div>
      <div class="notice-meta">${createdAtLocal}</div>
      <div class="notice-actions inline">
        <button class="button ghost" data-action="resolve">Resolve</button>
        <button class="button ghost" data-action="snooze">Snooze 2h</button>
      </div>
    `;
    const resolveBtn = row.querySelector('[data-action="resolve"]');
    const snoozeBtn = row.querySelector('[data-action="snooze"]');
    if (resolveBtn) {
      resolveBtn.addEventListener("click", async () => {
        try {
          await api(`/users/me/notifications/${item.id}`, {
            method: "PATCH",
            body: { status: "RESOLVED" },
          });
          await loadNotifications();
          await loadDashboard();
        } catch (e) {
          if (insightOut) insightOut.textContent = e.message;
        }
      });
    }
    if (snoozeBtn) {
      snoozeBtn.addEventListener("click", async () => {
        try {
          await api(`/users/me/notifications/${item.id}`, {
            method: "PATCH",
            body: { status: "SNOOZED", snooze_minutes: 120 },
          });
          await loadNotifications();
          await loadDashboard();
        } catch (e) {
          if (insightOut) insightOut.textContent = e.message;
        }
      });
    }
    notificationList.appendChild(row);
  }
}

function _sliceWindow(points, days) {
  const n = Number(days || 30);
  if (!Array.isArray(points) || points.length <= n) return points || [];
  return points.slice(points.length - n);
}

function _buildInteractiveChartSVG(
  points,
  { title = "", color = "#3b64ff", suffix = "" } = {},
) {
  const width = 860;
  const height = 300;
  const padL = 54;
  const padR = 22;
  const padT = 26;
  const padB = 48;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  if (!points.length) {
    return `
      <svg xmlns='http://www.w3.org/2000/svg' width='${width}' height='${height}'>
        <rect width='100%' height='100%' fill='#fff'/>
        <text x='50%' y='50%' text-anchor='middle' fill='#4a5f78' font-size='12' font-family='Manrope'>
          No user entries yet. Add your first record below to unlock trends.
        </text>
      </svg>
    `;
  }

  const values = points.map((p) => Number(p.value || 0));
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = Math.max(maxV - minV, 1e-6);
  const yMin = minV - range * 0.08;
  const yMax = maxV + range * 0.08;
  const yRange = Math.max(yMax - yMin, 1e-6);

  const px = (i) =>
    points.length === 1
      ? padL + plotW / 2
      : padL + (i / (points.length - 1)) * plotW;
  const py = (v) => padT + ((yMax - v) / yRange) * plotH;

  const linePts = points
    .map((p, i) => `${px(i).toFixed(1)},${py(Number(p.value || 0)).toFixed(1)}`)
    .join(" ");
  const circles = points
    .map(
      (p, i) =>
        `<circle cx='${px(i).toFixed(1)}' cy='${py(Number(p.value || 0)).toFixed(1)}' r='3.5' fill='${color}' />`,
    )
    .join("");

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((t) => {
    const yVal = yMin + (yMax - yMin) * t;
    const y = py(yVal);
    return `
      <line x1='${padL}' y1='${y.toFixed(1)}' x2='${width - padR}' y2='${y.toFixed(1)}' stroke='#e7eef8'/>
      <text x='${padL - 6}' y='${(y + 4).toFixed(1)}' text-anchor='end' fill='#6b7f95' font-size='9' font-family='Manrope'>
        ${yVal.toFixed(2)}${suffix}
      </text>
    `;
  });

  const xLabels = points
    .map((p, i) => {
      if (
        i !== 0 &&
        i !== points.length - 1 &&
        i % Math.ceil(points.length / 5) !== 0
      )
        return "";
      return `<text x='${px(i).toFixed(1)}' y='${height - 16}' text-anchor='middle' fill='#5d6f84' font-size='9' font-family='Manrope'>${p.label}</text>`;
    })
    .join("");

  return `
    <svg xmlns='http://www.w3.org/2000/svg' width='${width}' height='${height}'>
      <rect width='100%' height='100%' fill='#fff'/>
      <text x='${padL}' y='16' fill='#133f6b' font-size='12' font-family='Manrope' font-weight='700'>${title}</text>
      ${yTicks.join("")}
      <line x1='${padL}' y1='${height - padB}' x2='${width - padR}' y2='${height - padB}' stroke='#6b8bb3'/>
      <line x1='${padL}' y1='${padT}' x2='${padL}' y2='${height - padB}' stroke='#6b8bb3'/>
      <polyline points='${linePts}' fill='none' stroke='${color}' stroke-width='3'/>
      ${circles}
      ${xLabels}
    </svg>
  `;
}

function renderInteractiveChart() {
  if (!dashboardChart) return;
  const days = dashboardState.windowDays;
  const health = dashboardState.healthHistory || [];
  const risk = dashboardState.riskHistory || [];

  let points = [];
  let opts = { title: "Risk Trend", color: "#3b64ff", suffix: "" };
  if (dashboardState.chart === "risk") {
    points = _sliceWindow(
      risk
        .map((r) => ({
          label: String(r.created_at || "").slice(0, 10),
          value: Number(r.risk_score || 0),
        }))
        .reverse(),
      days,
    );
    opts = {
      title: `Risk Score (${days}d window)`,
      color: "#3b64ff",
      suffix: "",
    };
  } else if (dashboardState.chart === "glucose") {
    points = _sliceWindow(
      health
        .map((r) => ({
          label: String(r.record_date || "").slice(5),
          value: Number(r.blood_glucose || 0),
        }))
        .reverse(),
      days,
    );
    opts = {
      title: `Blood Glucose (${days}d window)`,
      color: "#20c5de",
      suffix: "",
    };
  } else if (dashboardState.chart === "steps") {
    points = _sliceWindow(
      health
        .map((r) => ({
          label: String(r.record_date || "").slice(5),
          value: Number(r.steps_count || 0),
        }))
        .reverse(),
      days,
    );
    opts = {
      title: `Daily Steps (${days}d window)`,
      color: "#4a52ff",
      suffix: "",
    };
  } else if (dashboardState.chart === "hydration") {
    points = _sliceWindow(
      health
        .map((r) => ({
          label: String(r.record_date || "").slice(5),
          value: Number(r.hydration_liters || 0),
        }))
        .reverse(),
      days,
    );
    opts = {
      title: `Hydration Liters (${days}d window)`,
      color: "#9c4fe8",
      suffix: "L",
    };
  }
  dashboardChart.innerHTML = _buildInteractiveChartSVG(points, opts);
}

async function loadInteractiveData() {
  if (!authToken) return;
  const [riskHistory, healthHistory] = await Promise.all([
    api("/my-risk-history"),
    api("/my-health"),
  ]);
  dashboardState.riskHistory = Array.isArray(riskHistory) ? riskHistory : [];
  dashboardState.healthHistory = Array.isArray(healthHistory)
    ? healthHistory
    : [];
  renderInteractiveChart();
  if (dashboardState.currentDashboard) renderKPIs(dashboardState.currentDashboard);
  renderDashboardEntryHint(dashboardState.currentDashboard);
}

async function loadDashboardInteractive() {
  if (!authToken) {
    setDashboardStatus("Login first.");
    return;
  }
  try {
    await Promise.all([loadDashboard(), loadInteractiveData()]);
    setDashboardStatus(
      `Dashboard synced at ${new Date().toLocaleTimeString()}`,
    );
  } catch (e) {
    setDashboardStatus(e.message);
  }
}

function setChartTabActive(chartKey) {
  dashboardState.chart = chartKey;
  for (const btn of chartTabButtons) {
    btn.classList.toggle("active", btn.dataset.chart === chartKey);
  }
  renderInteractiveChart();
}

function setModePillActive(windowDays) {
  const target = Number(windowDays || dashboardState.windowDays || 30);
  for (const btn of modePillButtons) {
    btn.classList.toggle(
      "active",
      Number(btn.dataset.windowPreset || 0) === target,
    );
  }
}

function setNotificationFilterActive(statusValue) {
  dashboardState.notificationFilter = statusValue;
  for (const btn of notificationFilterButtons) {
    btn.classList.toggle("active", btn.dataset.status === statusValue);
  }
}

function setAutoRefresh(enabled) {
  dashboardState.autoRefresh = Boolean(enabled);
  if (dashboardState.autoRefreshTimer) {
    window.clearInterval(dashboardState.autoRefreshTimer);
    dashboardState.autoRefreshTimer = null;
  }
  if (dashboardState.autoRefresh) {
    dashboardState.autoRefreshTimer = window.setInterval(
      loadDashboardInteractive,
      60000,
    );
  }
  if (toggleAutoRefreshBtn) {
    toggleAutoRefreshBtn.textContent = `Auto Refresh: ${dashboardState.autoRefresh ? "On" : "Off"}`;
  }
}

async function loadGraph() {
  if (!authToken) {
    if (trendGraph)
      trendGraph.innerHTML =
        "<p class='note'>Login required to render trend graph.</p>";
    return;
  }
  const res = await fetch(toApiUrl("/my-trends/graph"), {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`Graph load failed: ${res.status} ${txt}`);
  }
  if (trendGraph) trendGraph.innerHTML = await res.text();
}

async function loadLocation() {
  if (!authToken) {
    if (locationOut)
      locationOut.textContent = "Login first to manage location.";
    return;
  }
  try {
    const data = await api("/users/me/location");
    if (locationOut) locationOut.textContent = prettyLocation(data);
  } catch (e) {
    if (locationOut) locationOut.textContent = e.message;
  }
}

async function loadDailyPlan() {
  if (!authToken) return;
  try {
    const plan = await api("/users/me/daily-plan");
    renderDailyPlan(plan);
  } catch (e) {
    if (dailyPlanMeta) dailyPlanMeta.textContent = e.message;
  }
}

async function loadNotifications() {
  if (!authToken) return;
  try {
    const filter = dashboardState.notificationFilter || "ALL";
    const items = await api(
      `/users/me/notifications?status_filter=${encodeURIComponent(filter)}&limit=20`,
    );
    renderNotifications(items);
  } catch (e) {
    if (notificationList)
      notificationList.innerHTML = `<p class='note'>${e.message}</p>`;
  }
}

async function loadDashboard() {
  if (!authToken) {
    if (insightOut) insightOut.textContent = "Login first.";
    return;
  }
  try {
    const [dashboard, coach, usage] = await Promise.all([
      api("/users/me/dashboard"),
      api("/my/coach-cards"),
      api("/chatbot/usage"),
    ]);
    dashboardState.currentDashboard = dashboard;
    dashboardState.summaryLoaded = true;
    renderKPIs(dashboard);
    renderDailyPlan(dashboard.daily_plan);
    renderDashboardEntryHint(dashboard);
    if (insightOut)
      insightOut.textContent = pretty({ dashboard, coach, usage });
    await loadNotifications();
    await loadGraph();
  } catch (e) {
    if (insightOut) insightOut.textContent = e.message;
  }
}

function toIsoFromDateTimeLocal(value) {
  if (!value) return undefined;
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return undefined;
  return dt.toISOString();
}

async function startOAuth(provider) {
  try {
    const data = await api(`/integrations/wearables/${provider}/oauth/start`);
    window.location.href = data.auth_url;
  } catch (e) {
    if (wearableOut) wearableOut.textContent = e.message;
  }
}

async function loadIntel() {
  if (!authToken) {
    if (intelOut) intelOut.textContent = "Login first.";
    return;
  }
  try {
    const intel = await api("/users/me/live-intel");
    applyIntelVisualState(intel?.alert_level);
    speakLiveIntel(intel);
    if (intelOut) intelOut.textContent = pretty(intel);
  } catch (e) {
    applyIntelVisualState("NORMAL");
    if (intelOut) intelOut.textContent = e.message;
  }
}

document
  .getElementById("loadDashboardBtn")
  ?.addEventListener("click", loadDashboard);
loadDashboardBtnHero?.addEventListener("click", async () =>
  ensureWorkspaceOpen({ load: true }),
);
refreshDashboardAllBtn?.addEventListener("click", loadDashboardInteractive);
document.getElementById("loadRiskBtn")?.addEventListener("click", async () => {
  try {
    if (insightOut)
      insightOut.textContent = pretty(await api("/users/me/risk-summary"));
  } catch (e) {
    if (insightOut) insightOut.textContent = e.message;
  }
});
document.getElementById("loadUsageBtn")?.addEventListener("click", async () => {
  try {
    if (insightOut)
      insightOut.textContent = pretty(await api("/chatbot/usage"));
  } catch (e) {
    if (insightOut) insightOut.textContent = e.message;
  }
});
document.getElementById("loadCoachBtn")?.addEventListener("click", async () => {
  try {
    if (insightOut)
      insightOut.textContent = pretty(await api("/my/coach-cards"));
  } catch (e) {
    if (insightOut) insightOut.textContent = e.message;
  }
});
document.getElementById("loadIntelBtn")?.addEventListener("click", loadIntel);
loadDailyPlanBtn?.addEventListener("click", loadDailyPlan);
loadNotificationsBtn?.addEventListener("click", loadNotifications);
oauthGoogleBtn?.addEventListener("click", () => startOAuth("google_fit"));
oauthFitbitBtn?.addEventListener("click", () => startOAuth("fitbit"));
tourCloseBtn?.addEventListener("click", hideTour);
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
logoutBtn?.addEventListener("click", () => {
  closeUserMenu();
  authToken = "";
  localStorage.removeItem(TOKEN_KEY);
  setAuthState();
  window.location.href = withPageVersion("login.html");
});

dashboardWindowSelect?.addEventListener("change", () => {
  dashboardState.windowDays = Number(dashboardWindowSelect.value || 30);
  setModePillActive(dashboardState.windowDays);
  renderInteractiveChart();
});
toggleAutoRefreshBtn?.addEventListener("click", () =>
  setAutoRefresh(!dashboardState.autoRefresh),
);
toggleFocusModeBtn?.addEventListener("click", () => {
  dashboardState.focusMode = !dashboardState.focusMode;
  document.body.classList.toggle(
    "focus-dashboard-mode",
    dashboardState.focusMode,
  );
  toggleFocusModeBtn.textContent = dashboardState.focusMode
    ? "Exit Focus Mode"
    : "Focus Mode";
});
for (const btn of chartTabButtons) {
  btn.addEventListener("click", () =>
    setChartTabActive(btn.dataset.chart || "risk"),
  );
}
for (const btn of modePillButtons) {
  btn.addEventListener("click", async () => {
    const days = Number(btn.dataset.windowPreset || 30);
    dashboardState.windowDays = days;
    if (dashboardWindowSelect) dashboardWindowSelect.value = String(days);
    setModePillActive(days);
    renderInteractiveChart();
    await loadDashboardInteractive();
  });
}
for (const link of sectionNavLinks) {
  link.addEventListener("click", async (e) => {
    const id = getSectionIdFromHref(link.getAttribute("href"));
    if (!id) return;
    const target = document.getElementById(id);
    const page = SECTION_PAGE_MAP[id];
    if (!target && !page) return;
    e.preventDefault();
    await openSectionById(id);
  });
}
for (const btn of notificationFilterButtons) {
  btn.addEventListener("click", async () => {
    setNotificationFilterActive(btn.dataset.status || "ALL");
    await loadNotifications();
  });
}

openMobileGuideBtn?.addEventListener("click", async () => {
  closeUserMenu();
  await openSectionById("integrationsHub");
  setDashboardStatus(
    "Open Integrations Hub to connect wearables and push channels.",
  );
});
enterDashboardBtn?.addEventListener("click", async () =>
  openSectionById("interactiveDashboard"),
);
openWorkspaceTourBtn?.addEventListener("click", async () => {
  await ensureWorkspaceOpen({ load: true });
  showTour(true);
});
openFreeToolsBtn?.addEventListener("click", async () =>
  openSectionById("interactiveDashboard"),
);
openProToolsBtn?.addEventListener("click", async () =>
  openSectionById("integrationsHub"),
);
chatSpeakToggleBtn?.addEventListener("click", () => {
  chatUiState.ttsEnabled = !chatUiState.ttsEnabled;
  localStorage.setItem("pcube_tts_enabled", chatUiState.ttsEnabled ? "1" : "0");
  setChatSpeakToggleLabel();
});
chatVoiceBtn?.addEventListener("click", () => {
  const recognition = initSpeechRecognition();
  if (!recognition) {
    if (chatOut)
      chatOut.textContent = "Speech-to-text is not supported in this browser.";
    return;
  }
  try {
    if (chatUiState.listening) {
      recognition.stop();
    } else {
      recognition.start();
    }
  } catch (e) {
    if (chatOut) chatOut.textContent = e.message;
  }
});
startMotionStepBtn?.addEventListener("click", startMotionCounter);
stopMotionStepBtn?.addEventListener("click", stopMotionCounter);
resetMotionStepBtn?.addEventListener("click", resetMotionCounterToday);

listWearablesBtn?.addEventListener("click", async () => {
  try {
    if (wearableOut)
      wearableOut.textContent = pretty(await api("/integrations/wearables"));
  } catch (e) {
    if (wearableOut) wearableOut.textContent = e.message;
  }
});
listPushTokensBtn?.addEventListener("click", async () => {
  try {
    if (pushOut)
      pushOut.textContent = pretty(await api("/users/me/push-tokens"));
  } catch (e) {
    if (pushOut) pushOut.textContent = e.message;
  }
});
testPushBtn?.addEventListener("click", async () => {
  try {
    if (pushOut)
      pushOut.textContent = pretty(
        await api("/users/me/push-tokens/test", { method: "POST" }),
      );
  } catch (e) {
    if (pushOut) pushOut.textContent = e.message;
  }
});

registerForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(registerForm);
  const body = {
    email: String(fd.get("email") || "").trim(),
    full_name: String(fd.get("full_name") || "").trim(),
    password: String(fd.get("password") || ""),
  };
  try {
    const data = await api("/register", { method: "POST", body, auth: false });
    if (data.access_token) {
      authToken = data.access_token;
      localStorage.setItem(TOKEN_KEY, authToken);
      setAuthState();
      if (insightOut) insightOut.textContent = pretty(data);
      await loadDashboard();
      return;
    }
    if (data.otp_required) {
      if (insightOut) {
        insightOut.textContent =
          "Account created. Finish the one-time verification on the sign-up page before your first login.";
      }
      return;
    }
    if (insightOut) insightOut.textContent = pretty(data);
  } catch (err) {
    if (insightOut) insightOut.textContent = err.message;
  }
});

loginForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(loginForm);
  try {
    const data = await api("/login", {
      method: "POST",
      body: {
        email: String(fd.get("email") || "").trim(),
        password: String(fd.get("password") || ""),
      },
      auth: false,
    });
    authToken = data.access_token || "";
    if (!authToken) throw new Error("Login returned no access token");
    localStorage.setItem(TOKEN_KEY, authToken);
    setAuthState();
    if (insightOut) insightOut.textContent = "Login successful.";
    await loadLocation();
    await loadDashboard();
  } catch (err) {
    if (String(err?.message || "").includes(OTP_REQUIRED_ERROR_FRAGMENT)) {
      if (insightOut) {
        insightOut.textContent =
          "This new account still needs its one-time verification. Use the sign-up or login page to enter the code.";
      }
      return;
    }
    if (insightOut) insightOut.textContent = err.message;
  }
});

document
  .getElementById("enableLocationBtn")
  ?.addEventListener("click", async () => {
    if (!authToken) {
      if (locationOut) locationOut.textContent = "Login first.";
      return;
    }
    if (!navigator.geolocation) {
      if (locationOut)
        locationOut.textContent =
          "Geolocation is not available in this browser.";
      return;
    }
    try {
      await api("/users/me/location-permission", {
        method: "PATCH",
        body: { granted: true },
      });
      const pos = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 12000,
        });
      });
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      const capturedAt = new Date();
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
      if (locationOut) locationOut.textContent = err.message;
    }
  });

document
  .getElementById("disableLocationBtn")
  ?.addEventListener("click", async () => {
    try {
      const data = await api("/users/me/location-permission", {
        method: "PATCH",
        body: { granted: false },
      });
      if (locationOut) locationOut.textContent = prettyLocation(data);
    } catch (e) {
      if (locationOut) locationOut.textContent = e.message;
    }
  });

stepSyncForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(stepSyncForm);
  const sensorType = String(fd.get("sensor_type") || "STEP_COUNTER")
    .trim()
    .toUpperCase();
  const body = {
    device_id: String(fd.get("device_id") || "").trim() || "android-primary",
    sensor_type: sensorType,
    activity_minutes_delta: Number(fd.get("activity_minutes_delta") || 0),
    timezone:
      String(fd.get("timezone") || "").trim() ||
      Intl.DateTimeFormat().resolvedOptions().timeZone ||
      undefined,
  };
  const bootId = String(fd.get("boot_id") || "").trim();
  if (bootId) body.boot_id = bootId;

  const totalStepsSinceBoot = coerceNumber(fd.get("total_steps_since_boot"));
  if (totalStepsSinceBoot !== undefined)
    body.total_steps_since_boot = Math.max(0, Math.trunc(totalStepsSinceBoot));

  const detectedDelta = coerceNumber(fd.get("detected_steps_delta"));
  if (detectedDelta !== undefined)
    body.detected_steps_delta = Math.max(0, Math.trunc(detectedDelta));

  const legacyDelta = coerceNumber(fd.get("step_delta"));
  if (legacyDelta !== undefined)
    body.step_delta = Math.max(0, Math.trunc(legacyDelta));

  const algorithmVersion = String(fd.get("algorithm_version") || "").trim();
  if (algorithmVersion) body.algorithm_version = algorithmVersion;

  const confidence = coerceNumber(fd.get("confidence"));
  if (confidence !== undefined)
    body.confidence = Math.max(0, Math.min(1, Number(confidence)));

  const eventTime = toIsoFromDateTimeLocal(
    String(fd.get("event_time") || "").trim(),
  );
  if (eventTime) body.event_time = eventTime;

  const d = String(fd.get("record_date") || "").trim();
  if (d) body.record_date = d;

  if (
    sensorType === "STEP_COUNTER" &&
    body.total_steps_since_boot === undefined &&
    body.step_delta === undefined
  ) {
    if (stepOut)
      stepOut.textContent =
        "For STEP_COUNTER mode, provide total_steps_since_boot (or legacy step_delta).";
    return;
  }
  if (
    sensorType !== "STEP_COUNTER" &&
    body.detected_steps_delta === undefined &&
    body.step_delta === undefined &&
    (body.activity_minutes_delta || 0) <= 0
  ) {
    if (stepOut)
      stepOut.textContent =
        "Provide detected_steps_delta, step_delta, or activity_minutes_delta.";
    return;
  }

  try {
    const result = await api("/device/steps/sync", { method: "POST", body });
    if (stepOut) stepOut.textContent = pretty(result);
    stepSyncState.packetsSent += 1;
    stepSyncState.lastSyncAt = new Date();
    stepSyncState.lastMode = String(result.processing_mode || "-");
    stepSyncState.lastSensorType = String(
      result.sensor_type || sensorType || "-",
    );
    stepSyncState.lastAcceptedDelta = Number(result.accepted_step_delta || 0);
    stepSyncState.lastTotalSteps = Number(result.total_steps || 0);
    renderSensorStatus();
    await loadDashboard();
  } catch (err) {
    if (stepOut) stepOut.textContent = err.message;
  }
});

wearableConnectForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(wearableConnectForm);
  const body = {
    provider: String(fd.get("provider") || "").trim(),
  };
  const externalUserId = String(fd.get("external_user_id") || "").trim();
  const accessToken = String(fd.get("access_token") || "").trim();
  if (externalUserId) body.external_user_id = externalUserId;
  if (accessToken) body.access_token = accessToken;
  try {
    if (wearableOut)
      wearableOut.textContent = pretty(
        await api("/integrations/wearables/connect", { method: "POST", body }),
      );
  } catch (err) {
    if (wearableOut) wearableOut.textContent = err.message;
  }
});

wearableSyncForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(wearableSyncForm);
  const body = {
    provider: String(fd.get("provider") || "").trim(),
  };
  const dateVal = String(fd.get("record_date") || "").trim();
  if (dateVal) body.record_date = dateVal;
  for (const key of [
    "steps_count",
    "activity_minutes",
    "hydration_liters",
    "resting_heart_rate",
  ]) {
    const val = coerceNumber(fd.get(key));
    if (val !== undefined) body[key] = val;
  }
  try {
    if (wearableOut)
      wearableOut.textContent = pretty(
        await api("/integrations/wearables/sync", { method: "POST", body }),
      );
    await loadDashboard();
  } catch (err) {
    if (wearableOut) wearableOut.textContent = err.message;
  }
});

pushTokenForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(pushTokenForm);
  let pushToken = String(fd.get("push_token") || "").trim();
  let platform = String(fd.get("platform") || "").trim();
  const bridge = getFirebasePushBridge();
  if (!pushToken && bridge) {
    if (!platform) platform = "web";
    if (pushOut) {
      pushOut.textContent =
        "Requesting browser permission to register this device for push notifications...";
    }
    pushToken = String(await bridge.getBrowserPushToken()).trim();
  }
  const body = {
    provider: String(fd.get("provider") || "fcm").trim(),
    platform,
    push_token: pushToken,
  };
  const label = String(fd.get("device_label") || "").trim();
  if (label) body.device_label = label;
  if (!body.push_token) {
    if (pushOut) {
      pushOut.textContent =
        "Enter a push token manually, or configure Firebase Web Push so the browser can register one automatically.";
    }
    return;
  }
  if (!body.platform) body.platform = "web";
  try {
    if (pushOut)
      pushOut.textContent = pretty(
        await api("/users/me/push-tokens", { method: "POST", body }),
      );
    await loadDashboard();
  } catch (err) {
    if (pushOut) pushOut.textContent = err.message;
  }
});

shareForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(shareForm);
  const body = {
    expires_hours: Number(fd.get("expires_hours") || 72),
    lookback_days: Number(fd.get("lookback_days") || 30),
  };
  try {
    const out = await api("/users/me/share-links", { method: "POST", body });
    if (shareOut) shareOut.textContent = pretty(out);
    if (shareHint) {
      shareHint.textContent = `Share URL: ${out.share_url}\nView URL: ${out.view_url}\nPDF URL: ${out.pdf_url}`;
    }
  } catch (err) {
    if (shareOut) shareOut.textContent = err.message;
  }
});

healthForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(healthForm);
  const body = {
    record_date: String(fd.get("record_date") || ""),
    systolic_bp: Number(fd.get("systolic_bp")),
    diastolic_bp: Number(fd.get("diastolic_bp")),
    bmi: Number(fd.get("bmi")),
    blood_glucose: Number(fd.get("blood_glucose")),
    cholesterol: Number(fd.get("cholesterol")),
    smoking_status: String(fd.get("smoking_status") || ""),
    activity_level: String(fd.get("activity_level") || ""),
  };
  const optionalNumeric = [
    "steps_count",
    "activity_minutes",
    "resting_heart_rate",
    "hydration_liters",
  ];
  for (const key of optionalNumeric) {
    const val = coerceNumber(fd.get(key));
    if (val !== undefined) body[key] = val;
  }
  const city = String(fd.get("city") || "").trim();
  if (city) body.city = city;
  try {
    if (healthOut)
      healthOut.textContent = pretty(
        await api("/health-record", { method: "POST", body }),
      );
    healthForm.reset();
    setDashboardStatus("Health record saved. Refreshing your dashboard...");
    await loadDashboard();
    await loadInteractiveData();
  } catch (err) {
    if (healthOut) healthOut.textContent = err.message;
  }
});

chatForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(chatForm);
  const q = String(fd.get("question") || "").trim();
  if (!q) {
    if (chatOut) chatOut.textContent = "Question is required.";
    return;
  }
  appendChatBubble("user", q);
  if (chatTextInput) chatTextInput.value = "";
  const typingBubble = appendChatBubble("bot", "Thinking...", "typing");
  try {
    const result = await api("/chat", { method: "POST", body: { message: q } });
    if (typingBubble) typingBubble.remove();
    appendChatBubble("bot", String(result.response || ""));
    speakChatText(String(result.response || ""));
    if (chatOut) chatOut.textContent = pretty(result);
  } catch (err) {
    if (typingBubble) typingBubble.remove();
    appendChatBubble("error", err.message, "error");
    if (chatOut) chatOut.textContent = err.message;
  }
});

chatImageForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(chatImageForm);
  const q = String(fd.get("question") || "").trim();
  const file = fd.get("image");
  if (!q) {
    if (chatOut) chatOut.textContent = "Question is required.";
    return;
  }
  if (!(file instanceof File) || !file.size) {
    if (chatOut) chatOut.textContent = "Select an image file.";
    return;
  }
  appendChatBubble("user", `[Image] ${q}`);
  const typingBubble = appendChatBubble("bot", "Analyzing image...", "typing");
  try {
    const base64 = await toBase64(file);
    const result = await api("/chatbot/ask-with-image", {
      method: "POST",
      body: {
        question: q,
        image_base64: base64,
        image_mime_type: file.type || "image/jpeg",
      },
    });
    if (typingBubble) typingBubble.remove();
    appendChatBubble("bot", String(result.answer || ""));
    speakChatText(String(result.answer || ""));
    if (chatOut) chatOut.textContent = pretty(result);
  } catch (err) {
    if (typingBubble) typingBubble.remove();
    appendChatBubble("error", err.message, "error");
    if (chatOut) chatOut.textContent = err.message;
  }
});

setAuthState();
renderWelcomeGreeting();
renderDashboardEntryHint();
renderSensorStatus();
loadMotionCounterState();
resetMotionCounterIfNewDay(false);
renderMotionStepStatus();
setModePillActive(dashboardState.windowDays);
setChatSpeakToggleLabel();
setChatVoiceButtonLabel();
setupUserMenu();
window.setInterval(() => resetMotionCounterIfNewDay(false), 60000);

if (!authToken) {
  window.location.replace("login.html");
} else {
  if (localStorage.getItem("pcube_motion_counter_enabled") === "1")
    startMotionCounter();
  const hashId = String(window.location.hash || "").replace("#", "");
  if (
    hashId &&
    [
      "interactiveDashboard",
      "alertHub",
      "integrationsHub",
      "stepCounterHub",
    ].includes(hashId)
  ) {
    ensureWorkspaceOpen({ load: true, scrollToId: hashId });
  } else {
    ensureWorkspaceOpen({ load: true });
  }
}

// -- Quick services buttons (added for dashboard options)
// Quick modal helper
function showQuickModal({
  title = "Input",
  help = "",
  showAge = false,
  showFile = false,
  placeholder = "",
} = {}) {
  return new Promise((resolve) => {
    const modal = document.getElementById("quickModal");
    const form = document.getElementById("quickModalForm");
    const titleEl = document.getElementById("quickModalTitle");
    const helpEl = document.getElementById("quickModalHelp");
    const textEl = document.getElementById("quickModalText");
    const ageWrap = document.querySelector(".modal-age");
    const ageEl = document.getElementById("quickModalAge");
    const fileWrap = document.querySelector(".modal-file");
    const fileEl = document.getElementById("quickModalFile");
    const cancelBtn = document.getElementById("quickModalCancel");

    if (!modal || !form || !textEl) return resolve(null);
    titleEl.textContent = title || "Input";
    helpEl.textContent = help || "";
    textEl.placeholder = placeholder || "";
    textEl.value = "";
    ageEl.value = "";
    if (showAge) ageWrap.classList.remove("hidden");
    else ageWrap.classList.add("hidden");
    if (showFile) fileWrap.classList.remove("hidden");
    else fileWrap.classList.add("hidden");
    fileEl.value = null;

    function cleanup() {
      modal.classList.add("hidden");
      cancelBtn.removeEventListener("click", onCancel);
      form.removeEventListener("submit", onSubmit);
    }

    function onCancel(e) {
      e?.preventDefault();
      cleanup();
      resolve(null);
    }

    async function onSubmit(e) {
      e.preventDefault();
      const text = String(textEl.value || "").trim();
      const age = ageEl ? (ageEl.value ? Number(ageEl.value) : null) : null;
      const file =
        fileEl && fileEl.files && fileEl.files.length ? fileEl.files[0] : null;
      cleanup();
      resolve({ text, age, file });
    }

    cancelBtn.addEventListener("click", onCancel);
    form.addEventListener("submit", onSubmit);
    modal.classList.remove("hidden");
    textEl.focus();
  });
}
// Quick modal helper
function showQuickModal({
  title = "Input",
  help = "",
  showAge = false,
  showFile = false,
  placeholder = "",
} = {}) {
  return new Promise((resolve) => {
    const modal = document.getElementById("quickModal");
    const form = document.getElementById("quickModalForm");
    const titleEl = document.getElementById("quickModalTitle");
    const helpEl = document.getElementById("quickModalHelp");
    const textEl = document.getElementById("quickModalText");
    const ageWrap = document.querySelector(".modal-age");
    const ageEl = document.getElementById("quickModalAge");
    const fileWrap = document.querySelector(".modal-file");
    const fileEl = document.getElementById("quickModalFile");
    const cancelBtn = document.getElementById("quickModalCancel");

    if (!modal || !form || !textEl) return resolve(null);
    titleEl.textContent = title || "Input";
    helpEl.textContent = help || "";
    textEl.placeholder = placeholder || "";
    textEl.value = "";
    ageEl.value = "";
    if (showAge) ageWrap.classList.remove("hidden");
    else ageWrap.classList.add("hidden");
    if (showFile) fileWrap.classList.remove("hidden");
    else fileWrap.classList.add("hidden");
    fileEl.value = null;

    function cleanup() {
      modal.classList.add("hidden");
      cancelBtn.removeEventListener("click", onCancel);
      form.removeEventListener("submit", onSubmit);
    }

    function onCancel(e) {
      e?.preventDefault();
      cleanup();
      resolve(null);
    }

    async function onSubmit(e) {
      e.preventDefault();
      const text = String(textEl.value || "").trim();
      const age = ageEl ? (ageEl.value ? Number(ageEl.value) : null) : null;
      const file =
        fileEl && fileEl.files && fileEl.files.length ? fileEl.files[0] : null;
      cleanup();
      resolve({ text, age, file });
    }

    cancelBtn.addEventListener("click", onCancel);
    form.addEventListener("submit", onSubmit);
    modal.classList.remove("hidden");
    textEl.focus();
  });
}
const quickToolButtons = Array.from(
  document.querySelectorAll(".service-card[data-target]"),
);
for (const btn of quickToolButtons) {
  btn.addEventListener("click", () => {
    const target = String(btn.getAttribute("data-target") || "").trim();
    if (!target) return;
    window.location.href = withPageVersion(target);
  });
}

