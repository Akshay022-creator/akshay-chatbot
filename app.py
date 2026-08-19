import os
import uuid
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from groq import Groq

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise SystemExit(
        "Error: Set the GROQ_API_KEY environment variable before running this script.\n"
        "  export GROQ_API_KEY=\"your-key-here\""
    )

client = Groq(api_key=GROQ_API_KEY)

app = Flask(__name__)
# Needed so Flask can set a signed session cookie (used to give each visitor
# their own conversation history). Set FLASK_SECRET_KEY in production.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# Password for the /admin page where you read chat logs. SET THIS on Render
# (Environment Variables -> ADMIN_PASSWORD) — don't leave the default in
# production.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

BOT_NAME = "Akshay"

PREFERRED_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
]

# This is the personality of the bot. Edit this freely — it's the single
# biggest lever for making it actually sound like you instead of a generic
# assistant. Add real details: your actual projects, opinions, running
# jokes, how you'd really respond to stuff.
SYSTEM_PROMPT = """You are Akshay Kaushik — not a generic AI assistant, but a
digital version of Akshay himself, talking to whoever's on the site.

Who you are:
- CSE (Computer Science) student, into cybersecurity, Python, and generative AI.
- You've done coursework/projects around Python programming, algorithms,
  cybersecurity fundamentals, and generative AI / prompt engineering.
- You're building things, learning constantly, and genuinely enjoy this stuff —
  it's not a performance, it's real interest.

How you talk:
- Casual, warm, a bit witty. Mostly English, but you naturally drop in Kannada
  words typed in English (Kanglish) — things like "guru", "sari", "yenappa",
  "gothu illa" — the way a Kannadiga student actually talks, not forced into
  every single sentence. Use it when it feels natural, not as a gimmick.
- Straightforward, not corporate. No "I'd be happy to assist you today!"
  energy. Talk like a real person texting, not a customer support script.
- Short, punchy replies by default. Expand only when the topic actually
  needs it (like explaining a technical concept).

What you talk about:
- Anything — your interests (cybersecurity, Python, AI), your coursework,
  side projects, or just casual chit-chat like a friend would have.
- If someone asks something technical, answer it properly and clearly —
  being casual doesn't mean being vague or wrong.

Boundaries:
- If someone sincerely and directly asks whether you're a real person or an
  AI, be honest: you're an AI built to represent Akshay and chat the way he
  would, not the literal person. Don't insist you're human if pushed on it.
- Never make up specific personal facts you don't actually know (exact
  schedule, phone number, addresses, grades, etc.) — if asked, say you're
  not sure or redirect, don't fabricate.
"""

# Resolve the model once at startup instead of on every request.
_MODEL_CACHE = {"model": None}


def get_model():
    if _MODEL_CACHE["model"]:
        return _MODEL_CACHE["model"]

    models = client.models.list()
    available = [m.id for m in models.data]

    for candidate in PREFERRED_MODELS:
        if candidate in available:
            _MODEL_CACHE["model"] = candidate
            return candidate

    raise RuntimeError(
        "No compatible model was found. Available models: " + ", ".join(available)
    )


# ---------------------------------------------------------------------------
# Database (SQLite)
# ---------------------------------------------------------------------------
# NOTE on hosting: Render's free plan uses ephemeral disk — this file
# persists across restarts/spin-downs, but gets wiped on a fresh deploy
# (e.g. pushing new code). Fine for casual logging; for guaranteed
# permanence, switch to a hosted database (e.g. Render's free Postgres).
DB_PATH = os.environ.get("DB_PATH", "chats.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS visitors (
            session_id TEXT PRIMARY KEY,
            ip_address TEXT,
            user_agent TEXT,
            device TEXT,
            browser TEXT,
            os TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS threads (
            thread_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def parse_user_agent(ua):
    """Very small, dependency-free device/browser/OS guesser from the
    User-Agent header. Good enough for a personal dashboard — not as
    precise as a real parsing library, but needs zero extra installs."""
    ua_l = (ua or "").lower()

    if "iphone" in ua_l:
        device, os_name = "Mobile", "iOS (iPhone)"
    elif "ipad" in ua_l:
        device, os_name = "Tablet", "iOS (iPad)"
    elif "android" in ua_l:
        device = "Tablet" if "mobile" not in ua_l else "Mobile"
        os_name = "Android"
    elif "windows" in ua_l:
        device, os_name = "Desktop", "Windows"
    elif "mac os" in ua_l or "macintosh" in ua_l:
        device, os_name = "Desktop", "macOS"
    elif "linux" in ua_l:
        device, os_name = "Desktop", "Linux"
    else:
        device, os_name = "Unknown", "Unknown"

    if "edg/" in ua_l:
        browser = "Edge"
    elif "chrome/" in ua_l and "chromium" not in ua_l:
        browser = "Chrome"
    elif "crios" in ua_l:
        browser = "Chrome (iOS)"
    elif "fxios" in ua_l:
        browser = "Firefox (iOS)"
    elif "firefox/" in ua_l:
        browser = "Firefox"
    elif "safari/" in ua_l and "chrome/" not in ua_l:
        browser = "Safari"
    else:
        browser = "Unknown"

    return device, browser, os_name


def upsert_visitor(session_id, ip_address, user_agent):
    device, browser, os_name = parse_user_agent(user_agent)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    existing = conn.execute(
        "SELECT session_id FROM visitors WHERE session_id = ?", (session_id,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE visitors SET last_seen = ?, ip_address = ? WHERE session_id = ?",
            (now, ip_address, session_id),
        )
    else:
        conn.execute(
            """INSERT INTO visitors
               (session_id, ip_address, user_agent, device, browser, os, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, ip_address, user_agent, device, browser, os_name, now, now),
        )
    conn.commit()
    conn.close()


def make_title(first_message):
    title = first_message.strip().replace("\n", " ")
    return (title[:42] + "…") if len(title) > 42 else (title or "New chat")


def create_thread(session_id, first_message):
    thread_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO threads (thread_id, session_id, title, created_at, last_at) VALUES (?, ?, ?, ?, ?)",
        (thread_id, session_id, make_title(first_message), now, now),
    )
    conn.commit()
    conn.close()
    return thread_id


def thread_belongs_to(thread_id, session_id):
    conn = get_db()
    row = conn.execute(
        "SELECT session_id FROM threads WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    conn.close()
    return row is not None and row["session_id"] == session_id


def touch_thread(thread_id):
    conn = get_db()
    conn.execute(
        "UPDATE threads SET last_at = ? WHERE thread_id = ?",
        (datetime.now(timezone.utc).isoformat(), thread_id),
    )
    conn.commit()
    conn.close()


def log_message(thread_id, session_id, role, content):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (thread_id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (thread_id, session_id, role, content, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------------------------
# Admin auth helper
# ---------------------------------------------------------------------------
def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view_func(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# In-memory conversation store (keyed by thread_id, not session_id — a
# visitor can have several threads). Fine for a single-process dev/demo
# server; swap for Redis/DB if you ever run multiple workers.
# ---------------------------------------------------------------------------
conversations = {}


def get_history(thread_id):
    if thread_id not in conversations:
        # Rebuild from the database if this thread existed before a
        # server restart (e.g. Render spinning back up after inactivity).
        conn = get_db()
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY id",
            (thread_id,),
        ).fetchall()
        conn.close()

        history = [{"role": "system", "content": SYSTEM_PROMPT}]
        history.extend({"role": r["role"], "content": r["content"]} for r in rows)
        conversations[thread_id] = history

    return conversations[thread_id]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Demo page showing the popup widget embedded in a normal site."""
    return render_template("index.html", bot_name=BOT_NAME)


@app.route("/chat", methods=["POST"])
def chat():
    if "sid" not in session:
        session["sid"] = str(uuid.uuid4())
    session_id = session["sid"]

    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
    user_agent = request.headers.get("User-Agent", "")
    upsert_visitor(session_id, ip_address, user_agent)

    data = request.get_json(force=True, silent=True) or {}
    user_message = (data.get("message") or "").strip()
    thread_id = data.get("thread_id")

    if not user_message:
        return jsonify({"error": "Message is empty."}), 400

    # Create a new thread if none was given, or if the given one isn't
    # actually owned by this visitor.
    if not thread_id or not thread_belongs_to(thread_id, session_id):
        thread_id = create_thread(session_id, user_message)

    history = get_history(thread_id)
    history.append({"role": "user", "content": user_message})
    log_message(thread_id, session_id, "user", user_message)

    try:
        model = get_model()
        response = client.chat.completions.create(
            model=model,
            messages=history,
        )
        answer = response.choices[0].message.content
        history.append({"role": "assistant", "content": answer})
        log_message(thread_id, session_id, "assistant", answer)
        touch_thread(thread_id)
        return jsonify({"reply": answer, "bot_name": BOT_NAME, "thread_id": thread_id})
    except Exception as exc:
        # Don't keep a dangling user turn if the call failed.
        history.pop()
        return jsonify({"error": str(exc)}), 500


@app.route("/threads", methods=["GET"])
def list_threads():
    """All past conversation threads for this visitor's browser, newest
    first — powers the 'previous chats' list in the widget."""
    session_id = session.get("sid")
    if not session_id:
        return jsonify({"threads": []})

    conn = get_db()
    rows = conn.execute(
        "SELECT thread_id, title, last_at FROM threads WHERE session_id = ? ORDER BY last_at DESC",
        (session_id,),
    ).fetchall()
    conn.close()

    return jsonify({
        "threads": [
            {"thread_id": r["thread_id"], "title": r["title"], "last_at": r["last_at"]}
            for r in rows
        ]
    })


@app.route("/threads/<thread_id>/messages", methods=["GET"])
def thread_messages(thread_id):
    session_id = session.get("sid")
    if not session_id or not thread_belongs_to(thread_id, session_id):
        return jsonify({"error": "Not found"}), 404

    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY id",
        (thread_id,),
    ).fetchall()
    conn.close()

    return jsonify({"messages": [{"role": r["role"], "content": r["content"]} for r in rows]})


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        entered = request.form.get("password", "")
        if entered == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        error = "Wrong password."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    thread_rows = conn.execute("SELECT * FROM threads ORDER BY last_at DESC").fetchall()
    message_rows = conn.execute("SELECT * FROM messages ORDER BY thread_id, id").fetchall()
    visitor_rows = conn.execute("SELECT * FROM visitors").fetchall()
    conn.close()

    visitors_by_session = {v["session_id"]: v for v in visitor_rows}

    messages_by_thread = {}
    for row in message_rows:
        messages_by_thread.setdefault(row["thread_id"], []).append(row)

    conversations_list = [
        {
            "thread_id": t["thread_id"],
            "title": t["title"],
            "last_at": t["last_at"],
            "messages": messages_by_thread.get(t["thread_id"], []),
            "visitor": visitors_by_session.get(t["session_id"]),
        }
        for t in thread_rows
    ]

    stats = {
        "visitor_count": len(visitor_rows),
        "conversation_count": len(thread_rows),
        "message_count": len(message_rows),
    }

    return render_template(
        "admin.html",
        conversations=conversations_list,
        bot_name=BOT_NAME,
        stats=stats,
    )


if __name__ == "__main__":
    # Locally this runs on port 5001 (5000 often conflicts with AirPlay on
    # Mac). Hosting platforms like Render set the PORT env var themselves.
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
