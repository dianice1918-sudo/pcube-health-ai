(() => {
  const TOKEN_KEY = "pcube_access_token";
  const API_BASE_KEY = "pcube_api_base";
  const PAGE_ASSET_VERSION = "20260407a";

  const form = document.getElementById("medicationPlanForm");
  const generatePlanBtn = document.getElementById("generatePlanBtn");
  const planStatus = document.getElementById("planStatus");
  const usageSummary = document.getElementById("usageSummary");
  const overviewOut = document.getElementById("overviewOut");
  const supportiveCareOut = document.getElementById("supportiveCareOut");
  const medicationOptionsOut = document.getElementById("medicationOptionsOut");
  const interactionOut = document.getElementById("interactionOut");
  const followUpOut = document.getElementById("followUpOut");
  const safetyNoteOut = document.getElementById("safetyNoteOut");

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

  if (!authToken) {
    redirectToLogin();
    return;
  }

  function setStatus(message, tone = "") {
    if (!planStatus) return;
    planStatus.textContent = message;
    planStatus.className = "status-pill";
    if (tone) planStatus.classList.add(tone);
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function cleanOutputText(text, { stripListMarker = false } = {}) {
    let value = String(text || "").trim();
    value = value.replace(/^#{1,6}\s*/, "");
    if (stripListMarker) {
      value = value.replace(/^(?:[-*\u2022]\s+|\d+[.)]\s+)/, "");
    }
    value = value.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
    return value.trim();
  }

  function formatInlineHtml(text) {
    return escapeHtml(text)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/__([^_]+)__/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>")
      .replace(/_([^_]+)_/g, "<em>$1</em>");
  }

  function setRichText(target, lines, fallbackText, options = {}) {
    if (!target) return;
    const values = Array.isArray(lines)
      ? lines
          .map((line) => cleanOutputText(line, options))
          .filter((line) => line)
      : [];
    const displayLines = values.length
      ? values
      : [cleanOutputText(fallbackText, options)];
    target.innerHTML = displayLines
      .map((line) => formatInlineHtml(line))
      .join("<br><br>");
  }

  function normalizeHeadingText(text) {
    return String(text || "")
      .trim()
      .replace(/^#{1,6}\s*/, "")
      .replace(/\*\*/g, "")
      .replace(/__/g, "")
      .replace(/`/g, "")
      .replace(/[\u2013\u2014]/g, "-")
      .replace(/\s+/g, " ")
      .replace(/^[:\-\s]+|[:\-\s]+$/g, "")
      .trim()
      .toLowerCase();
  }

  function parseHeadingLine(line, headingMap) {
    const stripped = String(line || "").trim().replace(/^#{1,6}\s*/, "").trim();
    if (!stripped) return null;

    const directKey = headingMap.get(normalizeHeadingText(stripped));
    if (directKey) {
      return { key: directKey, remainder: "" };
    }

    const colonIndex = stripped.indexOf(":");
    if (colonIndex < 0) return null;

    const key = headingMap.get(
      normalizeHeadingText(stripped.slice(0, colonIndex)),
    );
    if (!key) return null;

    return {
      key,
      remainder: stripped.slice(colonIndex + 1).trim(),
    };
  }

  function renderList(target, items, fallbackText, numbered = false) {
    if (!target) return;
    const values = Array.isArray(items)
      ? items
          .map((item) => cleanOutputText(item, { stripListMarker: true }))
          .filter((item) => item)
      : [];
    if (!values.length) {
      target.innerHTML = "";
      const li = document.createElement("li");
      const fallback = formatInlineHtml(
        cleanOutputText(fallbackText, { stripListMarker: true }),
      );
      if (numbered) {
        li.innerHTML = `<span>1.</span> ${fallback}`;
      } else {
        li.innerHTML = fallback;
      }
      target.appendChild(li);
      return;
    }

    target.innerHTML = "";
    values.forEach((item, index) => {
      const li = document.createElement("li");
      if (numbered) {
        const span = document.createElement("span");
        span.textContent = `${index + 1}.`;
        li.appendChild(span);
        li.insertAdjacentHTML("beforeend", ` ${formatInlineHtml(item)}`);
      } else {
        li.innerHTML = formatInlineHtml(item);
      }
      target.appendChild(li);
    });
  }

  function parseSections(answer) {
    const labels = {
      overview: "Overview",
      supportiveCare: "Supportive Care",
      medicationOptions: "Possible Medication Options",
      interactionNotes: "Interaction and Avoidance Notes",
      followUp: "Follow-up and Escalation",
      safetyNote: "Safety Note",
    };
    const sections = {
      overview: [],
      supportiveCare: [],
      medicationOptions: [],
      interactionNotes: [],
      followUp: [],
      safetyNote: [],
    };
    const headingMap = new Map(
      Object.entries(labels).map(([key, label]) => [
        normalizeHeadingText(label),
        key,
      ]),
    );

    let currentKey = "overview";
    const lines = String(answer || "").split(/\r?\n/);
    for (const rawLine of lines) {
      const line = String(rawLine || "").trim();
      if (!line) continue;
      const headingMatch = parseHeadingLine(line, headingMap);
      if (headingMatch) {
        currentKey = headingMatch.key || "overview";
        if (headingMatch.remainder) {
          sections[currentKey].push(headingMatch.remainder);
        }
        continue;
      }
      sections[currentKey].push(line);
    }
    return sections;
  }

  function renderPlan(answer, payload) {
    const sections = parseSections(answer);
    const overviewParts = sections.overview.length
      ? sections.overview
      : [answer || "No medication plan returned."];
    setRichText(overviewOut, overviewParts, "No medication plan returned.");

    renderList(
      supportiveCareOut,
      sections.supportiveCare,
      "Supportive care guidance was not returned.",
    );
    renderList(
      medicationOptionsOut,
      sections.medicationOptions,
      "Medication options were not returned.",
    );
    if (interactionOut) {
      const interactionLines = sections.interactionNotes.length
        ? sections.interactionNotes.join("\n")
        : "No specific interaction warnings were returned. Confirm allergies, age suitability, and current medication conflicts before taking anything new.";
      setRichText(interactionOut, String(interactionLines).split(/\r?\n/), "");
    }
    renderList(
      followUpOut,
      sections.followUp,
      "Seek in-person care promptly if symptoms are severe, clearly worsening, or not improving.",
      true,
    );

    const safetyLines = sections.safetyNote.length
      ? sections.safetyNote
      : [
          "This is educational guidance only and does not replace professional medical judgment.",
        ];
    setRichText(
      safetyNoteOut,
      safetyLines,
      "This is educational guidance only and does not replace professional medical judgment.",
    );

    if (usageSummary) {
      const complaint = String(payload.primary_complaint || "").trim();
      usageSummary.textContent = complaint
        ? `Medication AI plan ready for "${complaint}".`
        : "Medication AI plan ready.";
    }
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

  async function requestMedicationPlan(payload) {
    const res = await fetch(toApiUrl("/chatbot/medication-plan"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify(payload),
    });

    if (res.status === 401 || res.status === 403) {
      redirectToLogin();
      throw new Error("Session expired. Please login again.");
    }
    if (!res.ok) {
      throw new Error(await readErrorMessage(res, "Medication AI request failed."));
    }
    return res.json();
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form) return;

    const payload = {
      primary_complaint: String(form.primary_complaint?.value || "").trim(),
      age_range: String(form.age_range?.value || "").trim(),
      risk_level: String(form.risk_level?.value || "").trim(),
      allergies: String(form.allergies?.value || "").trim(),
      current_medications: String(form.current_medications?.value || "").trim(),
      additional_notes: String(form.additional_notes?.value || "").trim(),
    };

    if (!payload.primary_complaint) {
      setStatus("Primary complaint required", "error");
      if (usageSummary) usageSummary.textContent = "Enter the main symptom or complaint first.";
      return;
    }

    if (generatePlanBtn) generatePlanBtn.disabled = true;
    setStatus("Medication AI is thinking", "busy");
    if (usageSummary) {
      usageSummary.textContent =
        "Generating a safety-first medication guidance plan...";
    }

    try {
      authToken = localStorage.getItem(TOKEN_KEY) || "";
      if (!authToken) {
        redirectToLogin();
        return;
      }

      const result = await requestMedicationPlan(payload);
      renderPlan(String(result.answer || "").trim(), payload);
      const remaining =
        typeof result.remaining === "number" ? result.remaining : null;
      const model = String(result.llm_model || "").trim() || "medication-ai";
      setStatus("Plan ready", "success");
      if (usageSummary) {
        usageSummary.textContent =
          remaining === null
            ? `Medication AI (${model}) returned a plan.`
            : `Medication AI (${model}) returned a plan. Remaining AI requests this month: ${remaining}.`;
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Medication AI is unavailable.";
      setStatus("Request failed", "error");
      if (overviewOut) overviewOut.textContent = message;
      renderList(
        supportiveCareOut,
        [],
        "Try again after checking the backend connection and your session.",
      );
      renderList(
        medicationOptionsOut,
        [],
        "Medication options could not be generated right now.",
      );
      if (interactionOut) interactionOut.textContent = message;
      renderList(
        followUpOut,
        [],
        "If symptoms are severe or worsening, seek clinical care promptly.",
        true,
      );
      if (safetyNoteOut) {
        safetyNoteOut.textContent =
          "This tool provides educational guidance only and does not replace professional medical judgment.";
      }
      if (usageSummary) usageSummary.textContent = message;
    } finally {
      if (generatePlanBtn) generatePlanBtn.disabled = false;
    }
  });
})();
