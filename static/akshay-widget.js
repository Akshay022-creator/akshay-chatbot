/**
 * Akshay chat widget
 * Drop this file (+ akshay-widget.css) into any page and it will inject a
 * floating chat launcher in the bottom-right corner that talks to a
 * Flask backend at CHAT_ENDPOINT. Supports multiple saved conversation
 * threads per visitor (browser-based, no login), like a mini ChatGPT.
 *
 * Usage:
 *   <link rel="stylesheet" href="/static/akshay-widget.css">
 *   <script src="/static/akshay-widget.js" data-endpoint="/chat"></script>
 */
(function () {
  const scriptTag = document.currentScript;
  const CHAT_ENDPOINT = (scriptTag && scriptTag.dataset.endpoint) || "/chat";
  const THREADS_ENDPOINT = (scriptTag && scriptTag.dataset.threadsEndpoint) || "/threads";
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
          <button class="akshay-icon-btn" id="akshay-new-chat" aria-label="New chat" title="New chat">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </button>
          <button class="akshay-icon-btn" id="akshay-history" aria-label="Chat history" title="Past chats">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="9"></circle>
              <polyline points="12 7 12 12 15 14"></polyline>
            </svg>
          </button>
          <button class="akshay-close" id="akshay-close" aria-label="Close chat">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div class="akshay-history-panel" id="akshay-history-panel">
          <div class="akshay-history-title">Past chats</div>
          <div class="akshay-history-list" id="akshay-history-list"></div>
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

  function timeAgo(iso) {
    const then = new Date(iso).getTime();
    const diffMin = Math.max(1, Math.round((Date.now() - then) / 60000));
    if (diffMin < 60) return diffMin + "m ago";
    const diffHr = Math.round(diffMin / 60);
    if (diffHr < 24) return diffHr + "h ago";
    return Math.round(diffHr / 24) + "d ago";
  }

  function init() {
    const root = buildWidget();

    const launcher = root.querySelector("#akshay-launcher");
    const win = root.querySelector("#akshay-window");
    const closeBtn = root.querySelector("#akshay-close");
    const messages = root.querySelector("#akshay-messages");
    const input = root.querySelector("#akshay-input");
    const sendBtn = root.querySelector("#akshay-send");
    const newChatBtn = root.querySelector("#akshay-new-chat");
    const historyBtn = root.querySelector("#akshay-history");
    const historyPanel = root.querySelector("#akshay-history-panel");
    const historyList = root.querySelector("#akshay-history-list");

    let currentThreadId = null;
    let opened = false;

    function clearMessages() {
      messages.innerHTML = "";
    }

    function showGreeting() {
      clearMessages();
      addMessage(messages, `Hi! I'm ${BOT_NAME}, your AI assistant. How can I help?`, "bot");
    }

    async function loadThread(threadId) {
      currentThreadId = threadId;
      historyPanel.classList.remove("akshay-open");
      clearMessages();
      try {
        const res = await fetch(`/threads/${threadId}/messages`, { credentials: "same-origin" });
        const data = await res.json();
        (data.messages || []).forEach((m) => {
          addMessage(messages, m.content, m.role === "user" ? "user" : "bot");
        });
      } catch (err) {
        addMessage(messages, "Couldn't load that chat. " + err.message, "error");
      }
      input.focus();
    }

    async function refreshHistoryList() {
      historyList.innerHTML = `<div class="akshay-history-empty">Loading…</div>`;
      try {
        const res = await fetch(THREADS_ENDPOINT, { credentials: "same-origin" });
        const data = await res.json();
        const threads = data.threads || [];

        if (threads.length === 0) {
          historyList.innerHTML = `<div class="akshay-history-empty">No past chats yet.</div>`;
          return;
        }

        historyList.innerHTML = "";
        threads.forEach((t) => {
          const item = document.createElement("button");
          item.className = "akshay-history-item";
          if (t.thread_id === currentThreadId) item.classList.add("akshay-history-item-active");
          item.innerHTML = `
            <span class="akshay-history-item-title">${t.title}</span>
            <span class="akshay-history-item-time">${timeAgo(t.last_at)}</span>
          `;
          item.addEventListener("click", () => loadThread(t.thread_id));
          historyList.appendChild(item);
        });
      } catch (err) {
        historyList.innerHTML = `<div class="akshay-history-empty">Couldn't load past chats.</div>`;
      }
    }

    async function startFresh() {
      // If the current thread is still empty (no messages sent yet), don't
      // create clutter — just reuse it.
      currentThreadId = null;
      historyPanel.classList.remove("akshay-open");
      showGreeting();
      input.focus();
    }

    async function openMostRecentOrGreet() {
      try {
        const res = await fetch(THREADS_ENDPOINT, { credentials: "same-origin" });
        const data = await res.json();
        const threads = data.threads || [];
        if (threads.length > 0) {
          await loadThread(threads[0].thread_id);
          return;
        }
      } catch (err) {
        // fall through to greeting
      }
      showGreeting();
    }

    async function sendMessage(text) {
      addMessage(messages, text, "user");
      input.value = "";
      input.style.height = "auto";
      sendBtn.disabled = true;

      const typingEl = addTypingIndicator(messages);

      try {
        const res = await fetch(CHAT_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ message: text, thread_id: currentThreadId }),
        });
        const data = await res.json();
        typingEl.remove();

        if (!res.ok || data.error) {
          addMessage(messages, "Sorry, something went wrong: " + (data.error || res.statusText), "error");
        } else {
          addMessage(messages, data.reply, "bot");
          currentThreadId = data.thread_id || currentThreadId;
        }
      } catch (err) {
        typingEl.remove();
        addMessage(messages, "Sorry, I couldn't reach the server. " + err.message, "error");
      } finally {
        sendBtn.disabled = false;
        input.focus();
      }
    }

    function openWindow() {
      win.classList.add("akshay-open");
      if (!opened) {
        opened = true;
        openMostRecentOrGreet();
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

    newChatBtn.addEventListener("click", startFresh);

    historyBtn.addEventListener("click", () => {
      const isOpen = historyPanel.classList.toggle("akshay-open");
      if (isOpen) refreshHistoryList();
    });

    input.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 90) + "px";
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const text = input.value.trim();
        if (text) sendMessage(text);
      }
    });

    sendBtn.addEventListener("click", () => {
      const text = input.value.trim();
      if (text) sendMessage(text);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
