/**
 * Akshay chat widget
 * Drop this file (+ akshay-widget.css) into any page and it will inject a
 * floating chat launcher in the bottom-right corner that talks to a
 * Flask backend at CHAT_ENDPOINT.
 *
 * Usage:
 *   <link rel="stylesheet" href="/static/akshay-widget.css">
 *   <script src="/static/akshay-widget.js" data-endpoint="/chat"></script>
 */
(function () {
  const scriptTag = document.currentScript;
  const CHAT_ENDPOINT = (scriptTag && scriptTag.dataset.endpoint) || "/chat";
  const RESET_ENDPOINT = (scriptTag && scriptTag.dataset.resetEndpoint) || "/reset";
  const BOT_NAME = (scriptTag && scriptTag.dataset.botName) || "Akshay";

  function initials(name) {
    return name.trim().charAt(0).toUpperCase();
  }

  function buildWidget() {
    const root = document.createElement("div");
    root.id = "akshay-widget-root";

    root.innerHTML = `
      <div class="akshay-window" id="akshay-window">
        <div class="akshay-header">
          <div class="akshay-avatar">${initials(BOT_NAME)}</div>
          <div class="akshay-header-text">
            <div class="akshay-header-name">${BOT_NAME}</div>
            <div class="akshay-header-status"><span class="akshay-status-dot"></span>Online</div>
          </div>
          <button class="akshay-close" id="akshay-close" aria-label="Close chat">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        <div class="akshay-messages" id="akshay-messages"></div>
        <div class="akshay-input-row">
          <textarea class="akshay-input" id="akshay-input" rows="1"
            placeholder="Message ${BOT_NAME}..."></textarea>
          <button class="akshay-send" id="akshay-send" aria-label="Send message">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          </button>
        </div>
      </div>
      <button class="akshay-launcher" id="akshay-launcher" aria-label="Open chat">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
        </svg>
      </button>
    `;

    document.body.appendChild(root);
    return root;
  }

  function addMessage(container, text, type) {
    const el = document.createElement("div");
    el.className = "akshay-msg akshay-msg-" + type;
    el.textContent = text;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    return el;
  }

  function addTypingIndicator(container) {
    const el = document.createElement("div");
    el.className = "akshay-typing";
    el.innerHTML = "<span></span><span></span><span></span>";
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    return el;
  }

  async function sendMessage(container, input, sendBtn, text) {
    addMessage(container, text, "user");
    input.value = "";
    input.style.height = "auto";
    sendBtn.disabled = true;

    const typingEl = addTypingIndicator(container);

    try {
      const res = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      typingEl.remove();

      if (!res.ok || data.error) {
        addMessage(container, "Sorry, something went wrong: " + (data.error || res.statusText), "error");
      } else {
        addMessage(container, data.reply, "bot");
      }
    } catch (err) {
      typingEl.remove();
      addMessage(container, "Sorry, I couldn't reach the server. " + err.message, "error");
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  function init() {
    const root = buildWidget();

    const launcher = root.querySelector("#akshay-launcher");
    const win = root.querySelector("#akshay-window");
    const closeBtn = root.querySelector("#akshay-close");
    const messages = root.querySelector("#akshay-messages");
    const input = root.querySelector("#akshay-input");
    const sendBtn = root.querySelector("#akshay-send");

    let greeted = false;

    function openWindow() {
      win.classList.add("akshay-open");
      if (!greeted) {
        addMessage(messages, `Hi! I'm ${BOT_NAME}, your AI assistant. How can I help?`, "bot");
        greeted = true;
      }
      input.focus();
    }

    launcher.addEventListener("click", () => {
      if (win.classList.contains("akshay-open")) {
        win.classList.remove("akshay-open");
      } else {
        openWindow();
      }
    });

    closeBtn.addEventListener("click", () => {
      win.classList.remove("akshay-open");
    });

    input.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 90) + "px";
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const text = input.value.trim();
        if (text) sendMessage(messages, input, sendBtn, text);
      }
    });

    sendBtn.addEventListener("click", () => {
      const text = input.value.trim();
      if (text) sendMessage(messages, input, sendBtn, text);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
