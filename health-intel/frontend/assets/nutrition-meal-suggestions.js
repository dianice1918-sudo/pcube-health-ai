(() => {
  const TOKEN_KEY = "pcube_access_token";
  const API_BASE_KEY = "pcube_api_base";
  const PAGE_ASSET_VERSION = "20260323a";

  const planStatus = document.getElementById("planStatus");
  const planMessage = document.getElementById("planMessage");
  const nutritionLogForm = document.getElementById("nutritionLogForm");
  const saveNutritionLogBtn = document.getElementById("saveNutritionLogBtn");
  const entryDateInput = document.getElementById("entry-date");
  const todayCalories = document.getElementById("todayCalories");
  const todayWater = document.getElementById("todayWater");
  const calorieGoal = document.getElementById("calorieGoal");
  const waterGoal = document.getElementById("waterGoal");
  const healthContextOut = document.getElementById("healthContextOut");
  const recentLogsOut = document.getElementById("recentLogsOut");
  const plannerLock = document.getElementById("plannerLock");
  const plannerLockMessage = document.getElementById("plannerLockMessage");
  const plannerContent = document.getElementById("plannerContent");
  const plannerStatus = document.getElementById("plannerStatus");
  const plannerUsage = document.getElementById("plannerUsage");
  const nutritionPlanForm = document.getElementById("nutritionPlanForm");
  const generateNutritionPlanBtn = document.getElementById(
    "generateNutritionPlanBtn",
  );
  const nutritionOverviewOut = document.getElementById("nutritionOverviewOut");
  const mealPrioritiesOut = document.getElementById("mealPrioritiesOut");
  const suggestedMealsOut = document.getElementById("suggestedMealsOut");
  const recipeIdeasOut = document.getElementById("recipeIdeasOut");
  const watchoutsOut = document.getElementById("watchoutsOut");
  const nutritionSafetyOut = document.getElementById("nutritionSafetyOut");

  let authToken = localStorage.getItem(TOKEN_KEY) || "";
  let currentTier = "FREE";

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

  function setPlannerStatus(message, tone = "") {
    if (!plannerStatus) return;
    plannerStatus.textContent = message;
    plannerStatus.className = "status-pill";
    if (tone) plannerStatus.classList.add(tone);
  }

  function renderList(target, items, fallbackText) {
    if (!target) return;
    const values = Array.isArray(items)
      ? items.filter((item) => String(item || "").trim())
      : [];
    target.innerHTML = "";
    if (!values.length) {
      const li = document.createElement("li");
      li.textContent = fallbackText;
      target.appendChild(li);
      return;
    }
    values.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = String(item);
      target.appendChild(li);
    });
  }

  function formatNumber(value, digits = 0) {
    const num = Number(value);
    if (!Number.isFinite(num)) return digits > 0 ? "0.0" : "0";
    return num.toFixed(digits);
  }

  function formatLog(log) {
    const parts = [];
    const date = String(log.entry_date || "").trim();
    if (date) parts.push(date);
    const mealType = String(log.meal_type || "").trim();
    if (mealType) parts.push(mealType);
    const calories = Number(log.calories);
    if (Number.isFinite(calories) && calories > 0) parts.push(`${calories} cal`);
    const water = Number(log.water_liters);
    if (Number.isFinite(water) && water > 0) parts.push(`${water.toFixed(1)} L water`);
    const goals = String(log.goals || "").trim();
    if (goals) parts.push(`goal: ${goals}`);
    const symptoms = String(log.symptoms || "").trim();
    if (symptoms) parts.push(`symptoms: ${symptoms}`);
    const notes = String(log.notes || "").trim();
    if (notes) parts.push(`notes: ${notes}`);
    return parts.join(" | ");
  }

  function renderSummary(summary) {
    if (todayCalories) {
      todayCalories.textContent = String(summary.today_calories ?? 0);
    }
    if (todayWater) {
      todayWater.textContent = `${formatNumber(summary.today_water_liters, 1)} L`;
    }
    if (calorieGoal) {
      calorieGoal.textContent = String(summary.calorie_goal ?? 2000);
    }
    if (waterGoal) {
      waterGoal.textContent = `${formatNumber(summary.water_goal_liters, 1)} L`;
    }

    renderList(
      healthContextOut,
      summary.health_context,
      "Recent nutrition context will appear here after you log more data.",
    );
    renderList(
      recentLogsOut,
      Array.isArray(summary.recent_logs)
        ? summary.recent_logs.map((log) => formatLog(log))
        : [],
      "No nutrition logs yet. Save your first entry to start building history.",
    );

    if (planMessage) {
      const avgCalories =
        typeof summary.avg_daily_calories_7d === "number"
          ? ` 7-day calorie average: ${summary.avg_daily_calories_7d}.`
          : "";
      const avgWater =
        typeof summary.avg_daily_water_liters_7d === "number"
          ? ` 7-day water average: ${formatNumber(summary.avg_daily_water_liters_7d, 1)} L.`
          : "";
      planMessage.textContent = `${String(summary.pro_unlock_message || "").trim()}${avgCalories}${avgWater}`.trim();
    }
  }

  function showPlannerLock(message) {
    plannerContent?.classList.add("hidden");
    plannerLock?.classList.remove("hidden");
    if (plannerLockMessage) plannerLockMessage.textContent = message;
  }

  function showPlannerContent(message) {
    plannerLock?.classList.add("hidden");
    plannerContent?.classList.remove("hidden");
    if (plannerUsage && message) plannerUsage.textContent = message;
  }

  function parseSections(answer) {
    const labels = {
      overview: "Overview",
      mealPriorities: "Meal Priorities",
      suggestedMeals: "Suggested Meals",
      recipeIdeas: "Recipe Ideas",
      watchouts: "Watch-outs",
      safetyNote: "Safety Note",
    };
    const sections = {
      overview: [],
      mealPriorities: [],
      suggestedMeals: [],
      recipeIdeas: [],
      watchouts: [],
      safetyNote: [],
    };
    const headingMap = new Map(
      Object.entries(labels).map(([key, label]) => [label.toLowerCase(), key]),
    );

    let currentKey = "overview";
    const lines = String(answer || "").split(/\r?\n/);
    for (const rawLine of lines) {
      const line = String(rawLine || "").trim();
      if (!line) continue;
      const normalizedHeading = line.replace(/:$/, "").trim().toLowerCase();
      if (headingMap.has(normalizedHeading)) {
        currentKey = headingMap.get(normalizedHeading) || "overview";
        continue;
      }
      sections[currentKey].push(line.replace(/^[*-]\s*/, ""));
    }
    return sections;
  }

  function renderNutritionPlan(answer) {
    const sections = parseSections(answer);
    const overview = sections.overview.length
      ? sections.overview.join("\n")
      : answer || "No nutrition plan returned.";
    if (nutritionOverviewOut) nutritionOverviewOut.textContent = overview;
    renderList(
      mealPrioritiesOut,
      sections.mealPriorities,
      "Meal priorities will appear here.",
    );
    renderList(
      suggestedMealsOut,
      sections.suggestedMeals,
      "Suggested meals will appear here.",
    );
    renderList(
      recipeIdeasOut,
      sections.recipeIdeas,
      "Recipe ideas will appear here.",
    );
    if (watchoutsOut) {
      watchoutsOut.textContent = sections.watchouts.length
        ? sections.watchouts.join("\n")
        : "No special watch-outs were returned. Still review allergies and chronic conditions before changing your meals.";
    }
    if (nutritionSafetyOut) {
      nutritionSafetyOut.textContent = sections.safetyNote.length
        ? sections.safetyNote.join("\n")
        : "This tool provides educational nutrition guidance only and does not replace clinician or dietitian advice.";
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

  async function readUsage() {
    const res = await fetch(toApiUrl("/chatbot/usage"), {
      headers: { Authorization: `Bearer ${authToken}` },
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

  async function readSummary() {
    const res = await fetch(toApiUrl("/nutrition/summary"), {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (res.status === 401 || res.status === 403) {
      redirectToLogin();
      throw new Error("Session expired. Please login again.");
    }
    if (res.status === 404) {
      throw new Error(
        "The running backend is missing the latest Nutrition routes. Restart the API, then refresh this page.",
      );
    }
    if (!res.ok) {
      throw new Error(await readErrorMessage(res, "Could not load nutrition summary."));
    }
    return res.json();
  }

  async function createNutritionLog(payload) {
    const res = await fetch(toApiUrl("/nutrition/logs"), {
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
    if (res.status === 404) {
      throw new Error(
        "The running backend is missing the latest Nutrition routes. Restart the API, then refresh this page.",
      );
    }
    if (!res.ok) {
      throw new Error(await readErrorMessage(res, "Could not save nutrition entry."));
    }
    return res.json();
  }

  async function requestNutritionPlan(payload) {
    const res = await fetch(toApiUrl("/chatbot/nutrition-plan"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify(payload),
    });
    if (res.status === 401) {
      redirectToLogin();
      throw new Error("Session expired. Please login again.");
    }
    if (res.status === 403) {
      throw new Error(
        await readErrorMessage(
          res,
          "Nutrition AI meal planning is reserved for Pro and Enterprise plans.",
        ),
      );
    }
    if (res.status === 404) {
      throw new Error(
        "The running backend is missing the latest Nutrition routes. Restart the API, then refresh this page.",
      );
    }
    if (!res.ok) {
      throw new Error(
        await readErrorMessage(res, "Nutrition AI request failed."),
      );
    }
    return res.json();
  }

  async function refreshSummary() {
    const summary = await readSummary();
    renderSummary(summary);
    return summary;
  }

  nutritionLogForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!nutritionLogForm) return;

    const payload = {
      meal_type: String(nutritionLogForm.meal_type?.value || "").trim(),
      entry_date: String(nutritionLogForm.entry_date?.value || "").trim() || null,
      calories:
        nutritionLogForm.calories?.value === ""
          ? null
          : Number(nutritionLogForm.calories?.value || 0),
      water_liters:
        nutritionLogForm.water_liters?.value === ""
          ? null
          : Number(nutritionLogForm.water_liters?.value || 0),
      symptoms: String(nutritionLogForm.symptoms?.value || "").trim(),
      goals: String(nutritionLogForm.goals?.value || "").trim(),
      notes: String(nutritionLogForm.notes?.value || "").trim(),
    };

    if (
      !payload.meal_type &&
      payload.calories === null &&
      payload.water_liters === null &&
      !payload.symptoms &&
      !payload.goals &&
      !payload.notes
    ) {
      setStatus("Add a nutrition detail first", "error");
      return;
    }

    if (saveNutritionLogBtn) saveNutritionLogBtn.disabled = true;
    setStatus("Saving nutrition log", "busy");

    try {
      authToken = localStorage.getItem(TOKEN_KEY) || "";
      if (!authToken) {
        redirectToLogin();
        return;
      }
      await createNutritionLog(payload);
      await refreshSummary();
      setStatus("Nutrition entry saved", "success");
      nutritionLogForm.reset();
      if (entryDateInput) entryDateInput.valueAsDate = new Date();
    } catch (error) {
      setStatus("Could not save entry", "error");
      if (planMessage) {
        planMessage.textContent =
          error instanceof Error ? error.message : "Could not save nutrition entry.";
      }
    } finally {
      if (saveNutritionLogBtn) saveNutritionLogBtn.disabled = false;
    }
  });

  nutritionPlanForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!nutritionPlanForm) return;

    const payload = {
      goal: String(nutritionPlanForm.goal?.value || "").trim(),
      symptom_focus: String(nutritionPlanForm.symptom_focus?.value || "").trim(),
      dietary_preferences: String(
        nutritionPlanForm.dietary_preferences?.value || "",
      ).trim(),
      allergies: String(nutritionPlanForm.allergies?.value || "").trim(),
      budget_level: String(nutritionPlanForm.budget_level?.value || "").trim(),
      cooking_time: String(nutritionPlanForm.cooking_time?.value || "").trim(),
      additional_notes: String(
        nutritionPlanForm.additional_notes?.value || "",
      ).trim(),
    };

    if (!payload.goal) {
      setPlannerStatus("Goal required", "error");
      if (plannerUsage) {
        plannerUsage.textContent = "Enter a goal before generating a plan.";
      }
      return;
    }

    if (generateNutritionPlanBtn) generateNutritionPlanBtn.disabled = true;
    setPlannerStatus("Nutrition AI is thinking", "busy");
    if (plannerUsage) {
      plannerUsage.textContent =
        "Generating a symptom-aware meal plan and recipe starter list...";
    }

    try {
      authToken = localStorage.getItem(TOKEN_KEY) || "";
      if (!authToken) {
        redirectToLogin();
        return;
      }
      const result = await requestNutritionPlan(payload);
      renderNutritionPlan(String(result.answer || "").trim());
      const remaining =
        typeof result.remaining === "number" ? result.remaining : null;
      const model = String(result.llm_model || "").trim() || "nutrition-ai";
      setPlannerStatus("Plan ready", "success");
      if (plannerUsage) {
        plannerUsage.textContent =
          remaining === null
            ? `Nutrition AI (${model}) returned a meal plan.`
            : `Nutrition AI (${model}) returned a meal plan. Remaining AI requests this month: ${remaining}.`;
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Nutrition AI is unavailable right now.";
      setPlannerStatus("Request failed", "error");
      if (
        /reserved for Pro and Enterprise plans|nutrition ai meal planning/i.test(
          message,
        )
      ) {
        showPlannerLock(message);
      }
      if (nutritionOverviewOut) nutritionOverviewOut.textContent = message;
      renderList(
        mealPrioritiesOut,
        [],
        "Try again after checking your plan access and backend connection.",
      );
      renderList(
        suggestedMealsOut,
        [],
        "Suggested meals could not be generated right now.",
      );
      renderList(
        recipeIdeasOut,
        [],
        "Recipe ideas could not be generated right now.",
      );
      if (watchoutsOut) watchoutsOut.textContent = message;
      if (nutritionSafetyOut) {
        nutritionSafetyOut.textContent =
          "This tool provides educational nutrition guidance only and does not replace clinician or dietitian advice.";
      }
      if (plannerUsage) plannerUsage.textContent = message;
    } finally {
      if (generateNutritionPlanBtn) generateNutritionPlanBtn.disabled = false;
    }
  });

  async function init() {
    if (!authToken) {
      redirectToLogin();
      return;
    }

    if (entryDateInput) entryDateInput.valueAsDate = new Date();
    setStatus("Loading nutrition data", "busy");
    setPlannerStatus("Ready");

    try {
      const [summary, usage] = await Promise.all([readSummary(), readUsage()]);
      renderSummary(summary);
      currentTier = String(usage.plan_tier || "FREE").trim().toUpperCase() || "FREE";

      if (currentTier === "PRO" || currentTier === "ENTERPRISE") {
        setStatus("Pro nutrition active", "success");
        showPlannerContent(
          String(summary.pro_unlock_message || "").trim() ||
            `Your ${currentTier} plan includes Nutrition AI meal planning.`,
        );
      } else {
        setStatus("Free tracking active", "success");
        showPlannerLock(
          String(summary.pro_unlock_message || "").trim() ||
            "Free includes calorie and water tracking. Upgrade to Pro for Nutrition AI meal planning.",
        );
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Could not load the nutrition workspace.";
      setStatus("Load failed", "error");
      if (planMessage) planMessage.textContent = message;
      showPlannerLock(message);
    }
  }

  init();
})();
