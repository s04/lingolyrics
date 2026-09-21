/* One controller per page; HTMX fragments contain no executable scripts. */
(() => {
  "use strict";
  let socket = null;
  let reconnect = null;
  let tick = null;
  let cleanup = () => {};
  const notice = (message) => {
    const box = document.getElementById("notice");
    box.replaceChildren();
    const p = document.createElement("p");
    p.className = "notice-message";
    p.textContent = message;
    box.append(p);
  };

  function initializeLyrics() {
    cleanup();
    if (socket) {
      socket.onclose = null;
      socket.close();
      socket = null;
    }
    clearTimeout(reconnect);
    clearInterval(tick);
    const container = document.getElementById("lyrics-container");
    if (!container) {
      document.body.classList.remove("focus-mode");
      return;
    }
    const abort = new AbortController();
    cleanup = () => abort.abort();
    const on = (id, event, handler) =>
      document
        .getElementById(id)
        ?.addEventListener(event, handler, { signal: abort.signal });
    let position = Number(container.dataset.position) || 0;
    let playing = container.dataset.playing === "true";
    let syncedAt = performance.now();
    let active = null;
    const demo = container.dataset.demo === "true";
    const status = document.getElementById("playback-status");
    const lines = [...container.querySelectorAll(".lyric-line")];
    const currentPosition = () =>
      position + (playing ? (performance.now() - syncedAt) / 1000 : 0);
    function update() {
      const time = currentPosition();
      if (container.dataset.synced !== "true") return;
      const line = lines
        .filter((item) => Number(item.dataset.time) <= time)
        .at(-1);
      if (line !== active) {
        active?.classList.remove("active");
        active = line;
        active?.classList.add("active");
        if (
          active &&
          document.getElementById("follow-lyrics").checked &&
          playing
        ) {
          const top = active.offsetTop - container.offsetTop;
          container.scrollTo({
            top: Math.max(0, top - container.clientHeight / 3),
            behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
              ? "instant"
              : "smooth",
          });
        }
      }
      if (demo && playing && time >= Number(lines.at(-1).dataset.time) + 6) {
        playing = false;
        position = 0;
        syncedAt = performance.now();
        document.getElementById("demo-play").textContent = "▶ Play demo timer";
        status.textContent = "Demo finished · play again to follow the words";
      }
      if (playing)
        status.textContent = `${demo ? "Demo timer · no audio" : "Playing on Spotify"} · ${Math.floor(time / 60)}:${String(Math.floor(time % 60)).padStart(2, "0")}`;
    }
    on("show-translations", "change", (event) =>
      container.classList.toggle("hide-translations", !event.target.checked),
    );
    on("show-phonetics", "change", (event) =>
      container.classList.toggle("hide-phonetics", !event.target.checked),
    );
    on("focus-mode", "click", (event) => {
      const enabled = document.body.classList.toggle("focus-mode");
      event.currentTarget.setAttribute("aria-pressed", String(enabled));
    });
    document
      .getElementById("focus-mode")
      .setAttribute(
        "aria-pressed",
        String(document.body.classList.contains("focus-mode")),
      );
    on("copy-lyrics", "click", async () => {
      try {
        await navigator.clipboard.writeText(
          lines
            .map((line) => line.querySelector(".line-content").innerText)
            .join("\n\n"),
        );
        notice("Lyrics copied to clipboard.");
      } catch {
        notice("Clipboard access is unavailable. Use Download lyrics instead.");
      }
    });
    on("demo-play", "click", (event) => {
      position = currentPosition();
      syncedAt = performance.now();
      playing = !playing;
      event.currentTarget.textContent = playing
        ? "Ⅱ Pause demo timer"
        : "▶ Play demo timer";
      if (!playing) status.textContent = "Demo timer paused · no audio";
      update();
    });
    function connect() {
      if (abort.signal.aborted) return;
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`,
      );
      socket.onmessage = (event) => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        if (data.error || data.track_id !== container.dataset.trackId) {
          position = currentPosition();
          playing = false;
          status.textContent =
            data.error ||
            "Spotify changed tracks. Load from Spotify to follow the new song.";
          return;
        }
        position = Number(data.position) || 0;
        playing = Boolean(data.is_playing);
        syncedAt = performance.now();
        if (!playing) status.textContent = "Paused on Spotify";
        update();
      };
      socket.onclose = () => {
        position = currentPosition();
        playing = false;
        status.textContent = "Playback disconnected. Reconnecting…";
        reconnect = setTimeout(connect, 5000);
      };
    }
    if (!demo && container.dataset.trackId) connect();
    tick = setInterval(update, 250);
    update();
  }

  document
    .getElementById("language-search")
    .addEventListener("input", (event) => {
      const query = event.target.value.trim().toLowerCase();
      let visible = 0;
      document.querySelectorAll(".language-option").forEach((label) => {
        label.hidden =
          !label.dataset.language.includes(query) &&
          !label.querySelector("input").value.includes(query);
        if (!label.hidden) visible++;
      });
      document.getElementById("language-empty").hidden = visible > 0;
    });
  document.getElementById("profile").addEventListener("change", (event) => {
    document.getElementById("custom-model-field").hidden =
      event.target.value !== "openrouter/custom";
  });
  document.getElementById("settings-form").addEventListener("change", () => {
    document.getElementById("settings-status").textContent =
      "Unsaved changes. Save before translating.";
  });
  document
    .getElementById("load-models")
    .addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const status = document.getElementById("model-status");
      button.disabled = true;
      status.textContent = "Loading model catalog…";
      try {
        const response = await fetch("/models/openrouter");
        if (!response.ok) throw new Error();
        const data = await response.json();
        const options = data.models.map((model) => {
          const option = document.createElement("option");
          option.value = model.id;
          option.label = model.name;
          return option;
        });
        document
          .getElementById("openrouter-models")
          .replaceChildren(...options);
        status.textContent = `${options.length} models loaded. Type a provider or model name above.`;
      } catch {
        status.textContent =
          "Catalog unavailable. You can still enter a model ID manually.";
      } finally {
        button.disabled = false;
      }
    });
  document.body.addEventListener("click", (event) => {
    if (event.target.closest("[data-dismiss-notice]"))
      document.getElementById("notice").replaceChildren();
  });
  document.body.addEventListener("htmx:beforeRequest", (event) => {
    document.getElementById("notice").replaceChildren();
    if (event.detail.target.id === "workspace")
      document.getElementById("workspace").setAttribute("aria-busy", "true");
  });
  document.body.addEventListener("htmx:afterRequest", () =>
    document.getElementById("workspace").removeAttribute("aria-busy"),
  );
  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target.id === "workspace") initializeLyrics();
  });
  document.body.addEventListener("htmx:responseError", () =>
    notice(
      "The request failed. Your current lyrics are preserved. Please retry.",
    ),
  );
  document.body.addEventListener("htmx:sendError", () =>
    notice(
      "The app could not be reached. Check that the local server is running.",
    ),
  );
  window.addEventListener("pagehide", () => {
    cleanup();
    clearInterval(tick);
    clearTimeout(reconnect);
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
  });
  initializeLyrics();
})();
