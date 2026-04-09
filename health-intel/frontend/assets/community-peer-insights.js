(() => {
  const TOKEN_KEY = "pcube_access_token";
  const API_BASE_KEY = "pcube_api_base";
  const PAGE_ASSET_VERSION = "20260323a";

  const planStatus = document.getElementById("planStatus");
  const planMessage = document.getElementById("planMessage");
  const proLockPanel = document.getElementById("proLockPanel");
  const proContent = document.getElementById("proContent");
  const cohortSize = document.getElementById("cohortSize");
  const overviewOut = document.getElementById("overviewOut");
  const matchedTopicsOut = document.getElementById("matchedTopicsOut");
  const habitTrendsOut = document.getElementById("habitTrendsOut");
  const symptomPatternsOut = document.getElementById("symptomPatternsOut");
  const nutritionPatternsOut = document.getElementById("nutritionPatternsOut");
  const privacyOut = document.getElementById("privacyOut");

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

  function showLoadFailure(message) {
    proContent?.classList.add("hidden");
    proLockPanel?.classList.remove("hidden");
    setStatus("Load failed", "error");
    if (planMessage) planMessage.textContent = message;
  }

  function renderTopicPills(topics) {
    if (!matchedTopicsOut) return;
    matchedTopicsOut.innerHTML = "";
    const values = Array.isArray(topics)
      ? topics.filter((item) => String(item || "").trim())
      : [];
    if (!values.length) {
      const span = document.createElement("span");
      span.className = "topic-pill";
      span.textContent = "No direct overlap yet";
      matchedTopicsOut.appendChild(span);
      return;
    }
    values.forEach((topic) => {
      const span = document.createElement("span");
      span.className = "topic-pill";
      span.textContent = String(topic);
      matchedTopicsOut.appendChild(span);
    });
  }

  function renderInsightList(target, items, fallbackTitle, fallbackDetail) {
    if (!target) return;
    const values = Array.isArray(items) ? items : [];
    target.innerHTML = "";
    if (!values.length) {
      const li = document.createElement("li");
      li.innerHTML = `<strong>${fallbackTitle}</strong>${fallbackDetail}`;
      target.appendChild(li);
      return;
    }
    values.forEach((item) => {
      const li = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = String(item.title || "Insight");
      li.appendChild(title);
      li.append(String(item.detail || ""));
      const evidence = String(item.evidence || "").trim();
      if (evidence) {
        const span = document.createElement("span");
        span.textContent = evidence;
        li.appendChild(span);
      }
      target.appendChild(li);
    });
  }

  async function readErrorMessage(res, fallbackText) {
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const payload = await res.json().catch(() => null);
      if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
        return payload.detail.trim();
      }
    }
    const text = await res.text().catch(() => "");
    return text.trim() || fallbackText;
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

  async function readInsights() {
    const res = await fetch(toApiUrl("/community/peer-insights"), {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    });
    if (res.status === 401) {
      redirectToLogin();
      throw new Error("Session expired. Please login again.");
    }
    if (res.status === 403) {
      throw new Error(
        await readErrorMessage(
          res,
          "Community / Peer Insights is reserved for Pro and Enterprise plans.",
        ),
      );
    }
    if (res.status === 404) {
      throw new Error(
        "The running backend is missing the latest Community Insights route. Restart the API, then refresh this page.",
      );
    }
    if (!res.ok) {
      throw new Error(await readErrorMessage(res, "Could not load peer insights."));
    }
    return res.json();
  }

  function renderInsights(data) {
    if (cohortSize) {
      cohortSize.textContent = String(data.cohort_size ?? 0);
    }
    if (overviewOut) {
      overviewOut.textContent = String(data.overview || "No overview available.");
    }
    if (privacyOut) {
      privacyOut.textContent = String(
        data.privacy_note ||
          "Peer insights show anonymized cohort patterns only.",
      );
    }

    renderTopicPills(data.matched_topics);
    renderInsightList(
      habitTrendsOut,
      data.habit_trends,
      "No strong habit trend yet",
      "There is not enough recent structured peer activity to surface a habit comparison yet.",
    );
    renderInsightList(
      symptomPatternsOut,
      data.symptom_patterns,
      "No strong symptom pattern yet",
      "Recent peer activity is still too varied to show a stable symptom cluster.",
    );
    renderInsightList(
      nutritionPatternsOut,
      data.nutrition_patterns,
      "No clear nutrition pattern yet",
      "Peers have not logged enough meal detail yet to surface a reliable pattern.",
    );
  }

  async function init() {
    if (!authToken) {
      redirectToLogin();
      return;
    }

    try {
      const usage = await readUsage();
      const tier = String(usage.plan_tier || "").trim().toUpperCase();
      if (tier !== "PRO" && tier !== "ENTERPRISE") {
        showUpgradeLock(
          "Community / Peer Insights is reserved for Pro and Enterprise plans. Upgrade to unlock anonymized peer trends.",
        );
        return;
      }

      const insights = await readInsights();
      renderInsights(insights);
      showProContent(
        `Your ${tier} plan includes Community / Peer Insights. These patterns are anonymized and group-based.`,
      );
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Could not load peer insights.";
      if (/reserved for Pro and Enterprise plans/i.test(message)) {
        showUpgradeLock(message);
      } else {
        showLoadFailure(message);
      }
    }
  }

  init();
})();
