(() => {
  const TOKEN_KEY = "pcube_access_token";
  const API_BASE_KEY = "pcube_api_base";
  const PAGE_ASSET_VERSION = "20260323a";

  const planStatus = document.getElementById("planStatus");
  const planMessage = document.getElementById("planMessage");
  const proLockPanel = document.getElementById("proLockPanel");
  const proContent = document.getElementById("proContent");

  let authToken = localStorage.getItem(TOKEN_KEY) || "";

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
    const host = String(window.location.hostname || "");
    const port = String(window.location.port || "");
    if (host !== "127.0.0.1" && host !== "localhost") return false;
    if (!["5500", "5501", "5502"].includes(port)) return false;
    return !isApiServedFrontend();
  }

  function resolveApiBase() {
    const configured = String(localStorage.getItem(API_BASE_KEY) || "").trim();
    const normalized = configured ? configured.replace(/\/+$/, "") : "";
    const currentBase = sameOriginBase();
    if (normalized) {
      if (isLocalStaticDevPage() && currentBase && normalized === currentBase) {
        localStorage.setItem(API_BASE_KEY, "http://127.0.0.1:8000");
        return "http://127.0.0.1:8000";
      }
      return normalized;
    }
    if (window.location.protocol === "file:") return "http://127.0.0.1:8000";
    if (isLocalStaticDevPage()) return "http://127.0.0.1:8000";
    return "";
  }

  const API_BASE = resolveApiBase();

  function toApiUrl(path) {
    const normalized = String(path || "").startsWith("/")
      ? String(path)
      : `/${String(path || "")}`;
    return API_BASE ? `${API_BASE}${normalized}` : normalized;
  }

  function redirectToLogin() {
    localStorage.removeItem(TOKEN_KEY);
    window.location.replace(withPageVersion("login.html"));
  }

  function setStatus(message, tone = "") {
    if (!planStatus) return;
    planStatus.textContent = message;
    planStatus.className = "status-pill";
    if (tone) planStatus.classList.add(tone);
  }

  function showProContent(message) {
    proLockPanel?.classList.add("hidden");
    proContent?.classList.remove("hidden");
    setStatus("Pro active", "success");
    if (planMessage) planMessage.textContent = message;
  }

  function showUpgradeLock(message) {
    proContent?.classList.add("hidden");
    proLockPanel?.classList.remove("hidden");
    setStatus("Upgrade required", "error");
    if (planMessage) planMessage.textContent = message;
  }

  async function readUsage() {
    const res = await fetch(toApiUrl("/chatbot/usage"), {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    });
    if (res.status === 401 || res.status === 403) {
      redirectToLogin();
      throw new Error("Session expired. Please login again.");
    }
    if (!res.ok) {
      throw new Error("Could not verify your subscription plan.");
    }
    return res.json();
  }

  async function init() {
    if (!authToken) {
      redirectToLogin();
      return;
    }

    try {
      const usage = await readUsage();
      const tier = String(usage.plan_tier || "").trim().toUpperCase();
      if (tier === "PRO" || tier === "ENTERPRISE") {
        const remaining =
          typeof usage.image_remaining === "number"
            ? ` Image analysis capacity remaining this month: ${usage.image_remaining}.`
            : "";
        showProContent(`Your ${tier} plan includes Analyze Test Result.${remaining}`);
        return;
      }
      showUpgradeLock(
        "Analyze Test Result is reserved for Pro and Enterprise plans. Upgrade to unlock AI-supported lab review.",
      );
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Could not verify your subscription plan.";
      showUpgradeLock(message);
    }
  }

  init();
})();
