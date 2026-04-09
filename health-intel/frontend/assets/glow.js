(() => {
  // Lightweight shared visual helper.
  // Keep this file safe to load on every page even if no glow targets exist.
  const targets = Array.from(document.querySelectorAll("[data-glow]"));
  if (!targets.length) return;

  for (const el of targets) {
    el.classList.add("glow-ready");
  }
})();
