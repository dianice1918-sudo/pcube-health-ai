(() => {
  const STORAGE_KEY = "pcube_theme_mode";
  const controls = Array.from(document.querySelectorAll("[data-theme-control]"));
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function resolveTheme(mode) {
    if (mode === "light" || mode === "dark") return mode;
    return media && media.matches ? "dark" : "light";
  }

  function applyTheme(mode) {
    const resolved = resolveTheme(mode);
    document.body.classList.remove("theme-light", "theme-dark");
    document.body.classList.add(`theme-${resolved}`);
    document.body.dataset.themeMode = mode;
    syncControls(mode);
  }

  function getStoredMode() {
    const mode = localStorage.getItem(STORAGE_KEY);
    if (mode === "light" || mode === "dark" || mode === "system") return mode;
    return "dark";
  }

  function setMode(mode) {
    localStorage.setItem(STORAGE_KEY, mode);
    applyTheme(mode);
  }

  function getControlMode(control) {
    if (!control) return "system";
    const attrMode = String(control.dataset.themeControl || "").trim();
    if (attrMode === "light" || attrMode === "dark" || attrMode === "system") return attrMode;
    const value = String(control.value || "").trim();
    if (value === "light" || value === "dark" || value === "system") return value;
    return "system";
  }

  function syncControls(mode) {
    for (const control of controls) {
      const tag = String(control.tagName || "").toLowerCase();
      const type = String(control.type || "").toLowerCase();
      const controlMode = getControlMode(control);

      if (tag === "button") {
        const active = controlMode === mode;
        control.classList.toggle("active", active);
        control.setAttribute("aria-pressed", active ? "true" : "false");
        continue;
      }

      if (tag === "select") {
        control.value = mode;
        continue;
      }

      if (type === "radio") {
        control.checked = controlMode === mode;
      }
    }
  }

  for (const control of controls) {
    const tag = String(control.tagName || "").toLowerCase();
    if (tag === "button") {
      control.addEventListener("click", () => setMode(getControlMode(control)));
      continue;
    }
    control.addEventListener("change", () => setMode(getControlMode(control)));
  }

  if (media && typeof media.addEventListener === "function") {
    media.addEventListener("change", () => {
      if ((localStorage.getItem(STORAGE_KEY) || "dark") === "system") applyTheme("system");
    });
  } else if (media && typeof media.addListener === "function") {
    media.addListener(() => {
      if ((localStorage.getItem(STORAGE_KEY) || "dark") === "system") applyTheme("system");
    });
  }

  applyTheme(getStoredMode());
})();
