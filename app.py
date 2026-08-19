import os
import uuid

from flask import Flask, render_template, request, jsonify, session
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
# In-memory conversation store
# ---------------------------------------------------------------------------
# Keyed by a per-visitor session id (stored in a cookie). This is fine for a
# single-process dev/demo server. For production with multiple workers or
# restarts, swap this dict for Redis, a database, or similar.
conversations = {}


def get_history(session_id):
    if session_id not in conversations:
        conversations[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return conversations[session_id]


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

    data = request.get_json(force=True, silent=True) or {}
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "Message is empty."}), 400

    history = get_history(session_id)
    history.append({"role": "user", "content": user_message})

    try:
        model = get_model()
        response = client.chat.completions.create(
            model=model,
            messages=history,
        )
        answer = response.choices[0].message.content
        history.append({"role": "assistant", "content": answer})
        return jsonify({"reply": answer, "bot_name": BOT_NAME})
    except Exception as exc:
        # Don't keep a dangling user turn if the call failed.
        history.pop()
        return jsonify({"error": str(exc)}), 500


@app.route("/reset", methods=["POST"])
def reset():
    """Clear the current visitor's conversation history."""
    session_id = session.get("sid")
    if session_id and session_id in conversations:
        conversations.pop(session_id)
    return jsonify({"ok": True})


if __name__ == "__main__":
    # Locally this runs on port 5001 (5000 often conflicts with AirPlay on
    # Mac). Hosting platforms like Render set the PORT env var themselves.
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
