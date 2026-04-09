(() => {
  const API_BASE_KEY = "pcube_api_base";
  const SAME_ORIGIN_API_KEY = "pcube_same_origin_api";
  const PAGE_ASSET_VERSION = "20260323e";
  const LIVE_SERVER_PORTS = new Set(["5500", "5501", "5502"]);

  function sameOriginBase() {
    if (window.location.protocol === "file:") return "";
    return `${window.location.protocol}//${window.location.host}`.replace(
      /\/+$/,
      "",
    );
  }

  function shouldUseSameOriginApi() {
    const explicit = String(localStorage.getItem(SAME_ORIGIN_API_KEY) || "").trim();
    if (explicit === "1") return true;
    if (explicit === "0") return false;
    if (window.location.protocol === "file:") return false;
    return LIVE_SERVER_PORTS.has(String(window.location.port || ""));
  }

  function ensureApiBaseDefault() {
    const existing = String(localStorage.getItem(API_BASE_KEY) || "").trim();
    if (existing) return;

    const host = window.location.hostname;
    const isLocalHost = host === "127.0.0.1" || host === "localhost";
    const isLiveServer = LIVE_SERVER_PORTS.has(String(window.location.port || ""));
    if (shouldUseSameOriginApi()) {
      const base = sameOriginBase();
      if (base) {
        localStorage.setItem(API_BASE_KEY, base);
        return;
      }
    }
    if (window.location.protocol === "file:" || (isLocalHost && isLiveServer)) {
      localStorage.setItem(API_BASE_KEY, "http://127.0.0.1:8000");
    }
  }

  function withPageVersion(target) {
    const raw = String(target || "").trim();
    if (!raw) return raw;
    if (/^(https?:|mailto:|tel:|#)/i.test(raw)) return raw;

    const hashIndex = raw.indexOf("#");
    const hashPart = hashIndex >= 0 ? raw.slice(hashIndex) : "";
    const base = hashIndex >= 0 ? raw.slice(0, hashIndex) : raw;

    if (!/\.html(\?|$)/i.test(base)) return raw;
    if (/[?&]v=/.test(base)) return `${base}${hashPart}`;

    const separator = base.includes("?") ? "&" : "?";
    return `${base}${separator}v=${PAGE_ASSET_VERSION}${hashPart}`;
  }

  function activateRedirect(link) {
    const target = String(link.getAttribute("data-target") || "").trim();
    const fallbackHref = String(link.getAttribute("href") || "").trim();
    const raw = target || fallbackHref;
    if (!raw) return;

    const resolved = withPageVersion(raw);
    link.setAttribute("href", resolved);

    link.addEventListener("click", (event) => {
      if (event.defaultPrevented) return;
      if (event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      window.location.href = resolved;
    });
  }

  ensureApiBaseDefault();

  const links = Array.from(
    document.querySelectorAll("a.tool-link[data-target], a.brand[data-target]"),
  );
  for (const link of links) activateRedirect(link);
})();
