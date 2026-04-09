(function () {
  const createForm = document.getElementById("createKeyForm");
  const keyNameInput = document.getElementById("keyName");
  const createdKey = document.getElementById("createdKey");
  const keysList = document.getElementById("keysList");

  function pretty(data) {
    try {
      return JSON.stringify(data, null, 2);
    } catch (e) {
      return String(data);
    }
  }

  async function loadKeys() {
    keysList.textContent = "Loading...";
    try {
      const data = await api("/admin/api-keys", { method: "GET", auth: true });
      if (!Array.isArray(data) || data.length === 0) {
        keysList.textContent = "No API keys found.";
        return;
      }
      keysList.innerHTML = "";
      data.forEach((k) => {
        const el = document.createElement("div");
        el.className = "api-key-row";
        el.innerHTML = `
          <div style="display:flex;align-items:center;gap:12px">
            <div>
              <div><strong>${escapeHtml(k.name)}</strong></div>
              <div style="font-size:0.9em;color:#666">prefix: ${escapeHtml(k.key_prefix)} — created: ${escapeHtml(k.created_at || "-")}</div>
            </div>
            <div style="margin-left:auto">
              <button data-id="${k.id}" class="use-key">Use</button>
            </div>
          </div>
        `;
        keysList.appendChild(el);
      });
      // bind use buttons
      Array.from(keysList.querySelectorAll(".use-key")).forEach((btn) => {
        btn.addEventListener("click", async (e) => {
          const id = btn.getAttribute("data-id");
          // call the list again to find the raw key is not returned by list; inform user to create to get raw
          // We'll attempt to get latest keys and if API returns raw key (only on create) we handle that.
          // For now, store the prefix as a hint
          const row = btn.closest(".api-key-row");
          const prefix = row ? row.querySelector("div strong").textContent : "";
          // Save a small hint in localStorage (not the raw secret)
          localStorage.setItem("pcube_api_key_hint", prefix || "");
          alert(
            "Saved API key hint to localStorage.pcube_api_key_hint. To use a raw API key, create a new key and click Use on the displayed raw secret.",
          );
        });
      });
    } catch (err) {
      keysList.textContent = `Error loading keys: ${err?.message || err}`;
    }
  }

  function escapeHtml(s) {
    if (!s) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  createForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = String(keyNameInput.value || "").trim();
    if (!name) return alert("Enter a name for the key");
    try {
      createdKey.classList.add("hidden");
      const data = await api("/admin/api-keys", {
        method: "POST",
        body: { name },
        auth: true,
      });
      // API returns the raw api_key on create (api_key field)
      const raw = data?.api_key || null;
      createdKey.classList.remove("hidden");
      if (raw) {
        createdKey.innerHTML = `
          <div>API key created. Save this secret now — it will not be shown again.</div>
          <pre style="background:#f7f7f8;padding:8px;border-radius:4px;margin-top:8px">${escapeHtml(raw)}</pre>
          <div style="margin-top:8px"><button id="useRawKey">Use this key</button></div>
        `;
        const useBtn = document.getElementById("useRawKey");
        useBtn?.addEventListener("click", () => {
          localStorage.setItem("pcube_api_key", raw);
          alert("API key stored to localStorage.pcube_api_key");
        });
      } else {
        createdKey.textContent = "API key created (no raw secret returned).";
      }
      keyNameInput.value = "";
      await loadKeys();
    } catch (err) {
      createdKey.classList.remove("hidden");
      createdKey.textContent = `Error creating key: ${err?.message || err}`;
    }
  });

  // initial load
  document.addEventListener("DOMContentLoaded", () => {
    loadKeys();
  });
})();
