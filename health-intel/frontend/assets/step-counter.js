"use strict";

(() => {
  const STORAGE_KEY = "pcube_step_counter_state_v1";
  const AUTO_RESUME_KEY = "pcube_step_counter_auto_resume";
  const SESSION_GAP_MS = 10 * 60 * 1000;
  const MOTION_COOLDOWN_MS = 350;
  const HISTORY_RETENTION_DAYS = 60;
  const WALK_GOAL_STEPS = 5000;
  const ACTIVE_MINUTES_GOAL = 45;
  const STREAK_GOAL_DAYS = 7;

  const elements = {
    stepsToday: document.getElementById("stepsTodayValue"),
    totalSteps: document.getElementById("totalStepsValue"),
    activeMinutes: document.getElementById("activeMinutesValue"),
    caloriesBurned: document.getElementById("caloriesBurnedValue"),
    currentStreak: document.getElementById("currentStreakValue"),
    summary: document.getElementById("dailyPatternSummary"),
    timeline: document.getElementById("activityTimeline"),
    goalStepsTag: document.getElementById("goalStepsTag"),
    goalMinutesTag: document.getElementById("goalMinutesTag"),
    goalStreakTag: document.getElementById("goalStreakTag"),
    status: document.getElementById("motionTrackingStatus"),
    startBtn: document.getElementById("startTrackingBtn"),
    stopBtn: document.getElementById("stopTrackingBtn"),
  };

  if (!elements.stepsToday) return;

  const state = {
    currentDay: getLocalDateKey(),
    todaySteps: 0,
    totalSteps: 0,
    history: {},
    sessions: {},
    trackingActive: false,
    lastMotionAt: 0,
    lastMagnitude: null,
    midnightTimer: null,
  };

  function safeCount(value) {
    return Math.max(0, Math.trunc(Number(value) || 0));
  }

  function formatCount(value) {
    return new Intl.NumberFormat().format(safeCount(value));
  }

  function pad(value) {
    return String(value).padStart(2, "0");
  }

  function getLocalDateKey(date = new Date()) {
    return [
      date.getFullYear(),
      pad(date.getMonth() + 1),
      pad(date.getDate()),
    ].join("-");
  }

  function getDayFromOffset(offset) {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    date.setDate(date.getDate() + offset);
    return getLocalDateKey(date);
  }

  function formatClockTime(isoString) {
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return "--:--";
    return new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function sanitizeHistory(rawHistory) {
    if (!rawHistory || typeof rawHistory !== "object") return {};
    const cleanHistory = {};
    for (const [dateKey, value] of Object.entries(rawHistory)) {
      if (typeof dateKey !== "string") continue;
      cleanHistory[dateKey] = safeCount(value);
    }
    return cleanHistory;
  }

  function sanitizeSessions(rawSessions) {
    if (!rawSessions || typeof rawSessions !== "object") return {};
    const cleanSessions = {};
    for (const [dateKey, entries] of Object.entries(rawSessions)) {
      if (!Array.isArray(entries)) continue;
      cleanSessions[dateKey] = entries
        .map((entry) => ({
          startedAt: String(entry?.startedAt || ""),
          lastStepAt: String(entry?.lastStepAt || entry?.startedAt || ""),
          steps: safeCount(entry?.steps),
        }))
        .filter((entry) => entry.startedAt && entry.lastStepAt && entry.steps > 0);
    }
    return cleanSessions;
  }

  function pruneRetainedHistory() {
    const cutoff = getDayFromOffset(-HISTORY_RETENTION_DAYS);
    for (const dateKey of Object.keys(state.history)) {
      if (dateKey < cutoff) delete state.history[dateKey];
    }
    for (const dateKey of Object.keys(state.sessions)) {
      if (dateKey < cutoff) delete state.sessions[dateKey];
    }
  }

  function persistState() {
    state.history[state.currentDay] = safeCount(state.todaySteps);
    pruneRetainedHistory();
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        currentDay: state.currentDay,
        todaySteps: safeCount(state.todaySteps),
        totalSteps: safeCount(state.totalSteps),
        history: state.history,
        sessions: state.sessions,
      }),
    );
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return;
      state.currentDay = String(parsed.currentDay || getLocalDateKey());
      state.todaySteps = safeCount(parsed.todaySteps);
      state.totalSteps = safeCount(parsed.totalSteps);
      state.history = sanitizeHistory(parsed.history);
      state.sessions = sanitizeSessions(parsed.sessions);
      state.todaySteps = Math.max(
        state.todaySteps,
        safeCount(state.history[state.currentDay]),
      );
      if (state.totalSteps === 0) {
        const historicTotal = Object.values(state.history).reduce(
          (sum, value) => sum + safeCount(value),
          0,
        );
        state.totalSteps = historicTotal;
      }
    } catch {
      // Ignore malformed browser cache and rebuild from defaults.
    }
  }

  function setStatus(message) {
    if (elements.status) {
      elements.status.textContent = message;
    }
  }

  function getStepCountForDate(dateKey) {
    if (dateKey === state.currentDay) return safeCount(state.todaySteps);
    return safeCount(state.history[dateKey]);
  }

  function computeCurrentStreak() {
    let cursor = 0;
    let streak = 0;
    const todaySteps = getStepCountForDate(getDayFromOffset(0));
    if (todaySteps === 0) cursor = -1;
    while (getStepCountForDate(getDayFromOffset(cursor)) > 0) {
      streak += 1;
      cursor -= 1;
    }
    return streak;
  }

  function estimateActiveMinutes() {
    return Math.floor(safeCount(state.todaySteps) / 100);
  }

  function estimateCaloriesBurned() {
    return Math.round(safeCount(state.todaySteps) * 0.04);
  }

  function updateGoalTags() {
    const stepGap = Math.max(WALK_GOAL_STEPS - safeCount(state.todaySteps), 0);
    elements.goalStepsTag.textContent =
      stepGap === 0 ? "Goal reached" : `${formatCount(stepGap)} to go`;

    const minutesGap = Math.max(ACTIVE_MINUTES_GOAL - estimateActiveMinutes(), 0);
    elements.goalMinutesTag.textContent =
      minutesGap === 0 ? "Goal reached" : `${formatCount(minutesGap)} min to go`;

    const streak = computeCurrentStreak();
    const streakGap = Math.max(STREAK_GOAL_DAYS - streak, 0);
    elements.goalStreakTag.textContent =
      streakGap === 0 ? "Goal reached" : `${formatCount(streakGap)} days to go`;
  }

  function renderTimeline() {
    if (!elements.timeline) return;
    elements.timeline.innerHTML = "";
    const todaySessions = Array.isArray(state.sessions[state.currentDay])
      ? state.sessions[state.currentDay]
      : [];
    if (!todaySessions.length) {
      const empty = document.createElement("div");
      empty.className = "timeline-item empty";
      empty.textContent = "Your walk sessions for today will appear here.";
      elements.timeline.appendChild(empty);
      return;
    }

    todaySessions
      .slice(-4)
      .reverse()
      .forEach((session) => {
        const item = document.createElement("div");
        item.className = "timeline-item";

        const time = document.createElement("strong");
        time.textContent = formatClockTime(session.startedAt);

        const message = document.createTextNode(
          ` Walk session (${formatCount(session.steps)} steps)`,
        );

        item.appendChild(time);
        item.appendChild(message);
        elements.timeline.appendChild(item);
      });
  }

  function renderSummary() {
    const sessionsToday = Array.isArray(state.sessions[state.currentDay])
      ? state.sessions[state.currentDay]
      : [];
    if (safeCount(state.todaySteps) === 0) {
      elements.summary.textContent =
        "No walking activity has been recorded yet. Start tracking and move with your device to begin counting steps.";
      return;
    }

    const latestSession = sessionsToday[sessionsToday.length - 1];
    const sessionCount = sessionsToday.length;
    const lastSeen = latestSession
      ? ` Latest movement was detected at ${formatClockTime(latestSession.lastStepAt)}.`
      : "";

    elements.summary.textContent =
      `You have logged ${formatCount(state.todaySteps)} steps across ${formatCount(sessionCount)} walk session${sessionCount === 1 ? "" : "s"} today.${lastSeen}`;
  }

  function renderStats() {
    elements.stepsToday.textContent = formatCount(state.todaySteps);
    elements.totalSteps.textContent = formatCount(state.totalSteps);
    elements.activeMinutes.textContent = formatCount(estimateActiveMinutes());
    elements.caloriesBurned.textContent = formatCount(estimateCaloriesBurned());
    const streak = computeCurrentStreak();
    elements.currentStreak.textContent = `${formatCount(streak)} day${streak === 1 ? "" : "s"}`;
    updateGoalTags();
    renderSummary();
    renderTimeline();
    elements.startBtn.disabled = state.trackingActive;
    elements.stopBtn.disabled = !state.trackingActive;
  }

  function rolloverIfNeeded() {
    const today = getLocalDateKey();
    if (state.currentDay === today) return false;
    state.history[state.currentDay] = safeCount(state.todaySteps);
    state.currentDay = today;
    state.todaySteps = 0;
    state.lastMotionAt = 0;
    state.lastMagnitude = null;
    state.sessions[state.currentDay] = [];
    persistState();
    setStatus("Daily step count reset at 12:00 AM local time.");
    return true;
  }

  function scheduleMidnightReset() {
    if (state.midnightTimer) {
      window.clearTimeout(state.midnightTimer);
    }
    const now = new Date();
    const nextMidnight = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate() + 1,
      0,
      0,
      1,
      0,
    );
    state.midnightTimer = window.setTimeout(() => {
      rolloverIfNeeded();
      renderStats();
      scheduleMidnightReset();
    }, Math.max(1000, nextMidnight.getTime() - now.getTime()));
  }

  function saveAutoResume(enabled) {
    localStorage.setItem(AUTO_RESUME_KEY, enabled ? "1" : "0");
  }

  function shouldAutoResume() {
    return localStorage.getItem(AUTO_RESUME_KEY) === "1";
  }

  function recordStep() {
    rolloverIfNeeded();
    state.todaySteps += 1;
    state.totalSteps += 1;
    const nowIso = new Date().toISOString();
    const todaySessions = Array.isArray(state.sessions[state.currentDay])
      ? state.sessions[state.currentDay]
      : [];
    const lastSession = todaySessions[todaySessions.length - 1];
    if (
      lastSession &&
      Date.now() - Date.parse(lastSession.lastStepAt) <= SESSION_GAP_MS
    ) {
      lastSession.steps += 1;
      lastSession.lastStepAt = nowIso;
    } else {
      todaySessions.push({
        startedAt: nowIso,
        lastStepAt: nowIso,
        steps: 1,
      });
    }
    state.sessions[state.currentDay] = todaySessions.slice(-12);
    persistState();
    setStatus(
      `Tracking live. Last walking motion was detected at ${formatClockTime(nowIso)}.`,
    );
    renderStats();
  }

  function handleMotionEvent(event) {
    if (!state.trackingActive) return;
    rolloverIfNeeded();

    const now = Date.now();
    if (now - state.lastMotionAt < MOTION_COOLDOWN_MS) return;

    const ax = event?.acceleration?.x;
    const ay = event?.acceleration?.y;
    const az = event?.acceleration?.z;
    const hasLinearAcceleration = [ax, ay, az].some(
      (value) => typeof value === "number",
    );

    const gx = hasLinearAcceleration ? ax : event?.accelerationIncludingGravity?.x;
    const gy = hasLinearAcceleration ? ay : event?.accelerationIncludingGravity?.y;
    const gz = hasLinearAcceleration ? az : event?.accelerationIncludingGravity?.z;

    if (![gx, gy, gz].some((value) => typeof value === "number")) return;

    const magnitude = Math.sqrt(
      (Number(gx) || 0) ** 2 +
        (Number(gy) || 0) ** 2 +
        (Number(gz) || 0) ** 2,
    );

    if (state.lastMagnitude == null) {
      state.lastMagnitude = magnitude;
      return;
    }

    const deltaMagnitude = Math.abs(magnitude - state.lastMagnitude);
    state.lastMagnitude = magnitude;
    const threshold = hasLinearAcceleration ? 0.85 : 1.15;
    if (deltaMagnitude < threshold) return;

    state.lastMotionAt = now;
    recordStep();
  }

  function stopTracking() {
    window.removeEventListener("devicemotion", handleMotionEvent);
    state.trackingActive = false;
    state.lastMagnitude = null;
    saveAutoResume(false);
    setStatus("Tracking stopped. Your saved steps remain available on this page.");
    renderStats();
  }

  async function startTracking(interactive = true) {
    rolloverIfNeeded();

    if (typeof window === "undefined" || !("DeviceMotionEvent" in window)) {
      setStatus("Device motion is not supported in this browser.");
      renderStats();
      return;
    }

    if (state.trackingActive) {
      renderStats();
      return;
    }

    try {
      const requestPermission = window.DeviceMotionEvent?.requestPermission;
      if (typeof requestPermission === "function") {
        if (!interactive) {
          setStatus("Tap Start Tracking to allow motion access on this device.");
          renderStats();
          return;
        }
        const permission = await requestPermission.call(window.DeviceMotionEvent);
        if (permission !== "granted") {
          saveAutoResume(false);
          setStatus("Motion access was denied, so step tracking could not start.");
          renderStats();
          return;
        }
      }

      window.addEventListener("devicemotion", handleMotionEvent, {
        passive: true,
      });
      state.trackingActive = true;
      saveAutoResume(true);
      setStatus(
        "Tracking started. Steps will increase from 0 only when walking motion is detected.",
      );
      renderStats();
    } catch (error) {
      saveAutoResume(false);
      setStatus("Motion tracking could not be started on this device.");
      renderStats();
      console.error(error);
    }
  }

  loadState();
  rolloverIfNeeded();
  persistState();
  renderStats();
  scheduleMidnightReset();

  if (shouldAutoResume()) {
    startTracking(false);
  } else {
    setStatus(
      "Step count starts at 0 and increases only when this page detects walking motion.",
    );
  }

  elements.startBtn?.addEventListener("click", () => {
    startTracking(true);
  });

  elements.stopBtn?.addEventListener("click", () => {
    stopTracking();
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && rolloverIfNeeded()) {
      renderStats();
    }
  });
})();
