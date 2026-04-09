"use strict";

(() => {
  const TOKEN_KEY = "pcube_access_token";
  const API_BASE_KEY = "pcube_api_base";
  const API_KEY_STORAGE = "pcube_api_key";
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

  const elements = {
    range: document.getElementById("range"),
    activityType: document.getElementById("activityType"),
    search: document.getElementById("search"),
    historyList: document.getElementById("historyList"),
    historyEmptyState: document.getElementById("historyEmptyState"),
    historyNote: document.getElementById("historyNote"),
    entriesLogged: document.getElementById("entriesLoggedValue"),
    mostFrequent: document.getElementById("mostFrequentValue"),
    lastUpdate: document.getElementById("lastUpdateValue"),
  };

  if (!elements.historyList) return;

  let authToken = localStorage.getItem(TOKEN_KEY) || "";
  let allEntries = [];
  let statusMessage = "";

  const STOPWORDS = new Set([
    "about",
    "after",
    "again",
    "also",
    "been",
    "body",
    "check",
    "checker",
    "days",
    "does",
    "feel",
    "feeling",
    "from",
    "have",
    "having",
    "help",
    "history",
    "image",
    "into",
    "just",
    "like",
    "need",
    "only",
    "pain",
    "please",
    "really",
    "should",
    "since",
    "symptom",
    "symptoms",
    "text",
    "that",
    "them",
    "this",
    "today",
    "what",
    "when",
    "with",
    "your",
  ]);

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

  function isApiServedFrontend() {
    const path = String(window.location.pathname || "");
    return path.startsWith("/frontend/") || path.startsWith("/app/");
  }

  function isLocalStaticDevPage() {
    if (window.location.protocol === "file:") return true;
    const isLocalHost =
      window.location.hostname === "127.0.0.1" ||
      window.location.hostname === "localhost";
    return isLocalHost && DEV_PORTS.has(String(window.location.port || "")) && !isApiServedFrontend();
  }

  function resolveApiBase() {
    const configured = normalizeApiBase(localStorage.getItem(API_BASE_KEY));
    if (configured) return configured;
    if (isLocalStaticDevPage()) return "http://127.0.0.1:8000";
    return sameOriginBase();
  }

  function toApiUrl(path) {
    const base = resolveApiBase();
    const suffix = path.startsWith("/") ? path : `/${path}`;
    return `${base}${suffix}`;
  }

  async function api(path) {
    const headers = {};
    if (authToken) headers.Authorization = `Bearer ${authToken}`;
    const apiKey = String(localStorage.getItem(API_KEY_STORAGE) || "").trim();
    if (apiKey) headers["X-API-Key"] = apiKey;

    const res = await fetch(toApiUrl(path), { headers });
    const contentType = res.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await res.json()
      : await res.text();

    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        authToken = "";
        window.location.replace("login.html");
        throw new Error("Session expired. Please login again.");
      }
      const detail =
        typeof payload === "string"
          ? payload
          : String(payload?.detail || "Request failed");
      throw new Error(detail);
    }

    return payload;
  }

  function normalizeQuestion(text) {
    return String(text || "")
      .replace(/^\[(Nutrition|Medication)\s+AI\]\s*/i, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function isSymptomActivity(item) {
    const question = String(item?.question || "").trim();
    if (!question) return false;
    if (/^\[(Nutrition|Medication)\s+AI\]/i.test(question)) return false;
    return true;
  }

  function getActivityType(item) {
    return item?.had_image ? "image" : "text";
  }

  function formatCount(value) {
    return new Intl.NumberFormat().format(Math.max(0, Number(value) || 0));
  }

  function formatDateTime(isoString) {
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return "Unknown";
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  }

  function formatRelativeDate(isoString) {
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return "Unknown";

    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfTarget = new Date(
      date.getFullYear(),
      date.getMonth(),
      date.getDate(),
    );
    const diffDays = Math.round(
      (startOfToday.getTime() - startOfTarget.getTime()) / 86400000,
    );

    if (diffDays <= 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    return `${diffDays} days ago`;
  }

  function truncate(text, maxLength = 88) {
    const clean = String(text || "").trim();
    if (clean.length <= maxLength) return clean;
    return `${clean.slice(0, maxLength - 3).trim()}...`;
  }

  function extractMostFrequent(entries) {
    const counts = new Map();

    entries.forEach((entry) => {
      const tokens = new Set(
        normalizeQuestion(entry.question)
          .toLowerCase()
          .match(/[a-z][a-z'-]{2,}/g) || [],
      );

      tokens.forEach((token) => {
        if (STOPWORDS.has(token)) return;
        counts.set(token, (counts.get(token) || 0) + 1);
      });
    });

    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    if (!sorted.length) return "None yet";
    const top = sorted[0][0];
    return top.charAt(0).toUpperCase() + top.slice(1);
  }

  function passesDateRange(entry, rangeValue) {
    if (rangeValue === "all") return true;
    const days = Number(rangeValue || 30);
    if (!Number.isFinite(days) || days <= 0) return true;
    const createdAt = new Date(entry.created_at);
    if (Number.isNaN(createdAt.getTime())) return false;
    const threshold = Date.now() - days * 86400000;
    return createdAt.getTime() >= threshold;
  }

  function getFilteredEntries() {
    const rangeValue = String(elements.range?.value || "30");
    const activityType = String(elements.activityType?.value || "all");
    const query = String(elements.search?.value || "")
      .trim()
      .toLowerCase();

    return allEntries.filter((entry) => {
      if (!passesDateRange(entry, rangeValue)) return false;
      if (activityType !== "all" && getActivityType(entry) !== activityType) {
        return false;
      }
      if (!query) return true;
      return normalizeQuestion(entry.question).toLowerCase().includes(query);
    });
  }

  function renderSummary(entries) {
    elements.entriesLogged.textContent = formatCount(entries.length);
    elements.mostFrequent.textContent = "";
    elements.lastUpdate.textContent = "";
  }

  function renderEntries(entries) {
    elements.historyList.innerHTML = "";

    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "history-empty";
      empty.textContent =
        allEntries.length > 0
          ? "No entries match your current filters."
          : "No symptom activity yet. Open the symptom checker to begin building your history.";
      elements.historyList.appendChild(empty);
      return;
    }

    const sorted = [...entries].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );

    sorted.forEach((entry) => {
      const article = document.createElement("article");
      article.className = "history-item";

      const title = document.createElement("h4");
      title.textContent = truncate(normalizeQuestion(entry.question));

      const body = document.createElement("p");
      body.textContent = `Logged from ${
        getActivityType(entry) === "image" ? "image" : "text"
      } symptom checker activity on ${formatDateTime(entry.created_at)}.`;

      const pills = document.createElement("div");
      pills.className = "pill-row";

      const typePill = document.createElement("span");
      typePill.className = "pill";
      typePill.textContent =
        getActivityType(entry) === "image" ? "Image check" : "Text check";

      const datePill = document.createElement("span");
      datePill.className = "pill";
      datePill.textContent = formatRelativeDate(entry.created_at);

      const statusPill = document.createElement("span");
      statusPill.className = "pill";
      statusPill.textContent = "User activity";

      pills.append(typePill, datePill, statusPill);
      article.append(title, body, pills);
      elements.historyList.appendChild(article);
    });
  }

  function render() {
    const filtered = getFilteredEntries();
    renderSummary(filtered);
    renderEntries(filtered);

    if (statusMessage) {
      elements.historyNote.textContent = statusMessage;
    } else if (allEntries.length) {
      elements.historyNote.textContent =
        "This history is built only from real symptom checker activity saved on your account.";
    } else {
      elements.historyNote.textContent =
        "This page starts fresh and updates only from real symptom checker activity on your account.";
    }
  }

  async function loadHistory() {
    if (!authToken) {
      window.location.replace("login.html");
      return;
    }

    try {
      const items = await api("/chatbot/history");
      allEntries = Array.isArray(items) ? items.filter(isSymptomActivity) : [];
      statusMessage = "";
      render();
    } catch (error) {
      statusMessage =
        error instanceof Error ? error.message : "Could not load symptom history.";
      allEntries = [];
      render();
    }
  }

  elements.range?.addEventListener("change", render);
  elements.activityType?.addEventListener("change", render);
  elements.search?.addEventListener("input", render);

  loadHistory();
})();
