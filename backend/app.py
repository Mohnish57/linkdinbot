"""Flask API backend for LinkedIn bot.

Run with: `python -m flask --app app run --port 5000`
Or: `gunicorn app:app`
"""
from __future__ import annotations

import os
import sys
import json
import threading
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import yaml
import pandas as pd

# Add parent to path so we can import linkedinBot
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from linkedinBot.bot import LinkedInBot

app = Flask(__name__)
CORS(app)  # Allow React frontend to call these APIs

CONFIG_PATH = PROJECT_ROOT / "linkedinBot" / "configs" / "config.yaml"
OUTPUT_DIR = PROJECT_ROOT / "linkedinBot" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = PROJECT_ROOT / "linkedinBot" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# In-memory bot status
bot_status = {"state": "idle", "message": "", "progress": ""}
bot_action_lock = threading.Lock()

CHROME_PROFILE_DIR = PROJECT_ROOT / "linkedinBot" / "chrome-profile"

def _cleanup_chrome_profile():
    """Kill orphan Chrome instances holding the bot's profile and remove stale lock files."""
    import subprocess
    try:
        subprocess.run(
            ["pkill", "-9", "-f", f"user-data-dir={CHROME_PROFILE_DIR}"],
            check=False, capture_output=True,
        )
    except FileNotFoundError:
        pass
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            (CHROME_PROFILE_DIR / name).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

_cleanup_chrome_profile()

def load_config():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}

def save_config(cfg: dict):
    with CONFIG_PATH.open("w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)

def deep_merge(base: dict, updates: dict):
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base

def set_status(state: str, message: str = "", progress: str = ""):
    global bot_status
    bot_status = {"state": state, "message": message, "progress": progress, "timestamp": datetime.now().isoformat()}

def resume_payload():
    resumes = {}
    for role in ("fullstack", "frontend"):
        matches = sorted(UPLOAD_DIR.glob(f"{role}_*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            latest = matches[0]
            resumes[role] = {
                "name": latest.name,
                "path": str(latest),
                "uploaded_at": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(),
            }
    return resumes

# ============================================================ Config endpoints
@app.route("/api/config", methods=["GET"])
def get_config():
    """Fetch current config."""
    cfg = load_config()
    return jsonify(cfg)

@app.route("/api/config", methods=["POST"])
def update_config():
    """Update config (settings, jobPreferences, candidate, etc)."""
    data = request.json
    cfg = load_config()
    deep_merge(cfg, data)
    save_config(cfg)
    return jsonify({"ok": True, "config": cfg})

@app.route("/api/shorten-url", methods=["POST"])
def shorten_url():
    """Shorten a URL with TinyURL."""
    data = request.json or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "url is required"}), 400

    try:
        tiny_url = "https://tinyurl.com/api-create.php?" + urllib.parse.urlencode({"url": url})
        with urllib.request.urlopen(tiny_url, timeout=10) as response:
            short_url = response.read().decode("utf-8").strip()
        if not short_url.startswith("http"):
            raise ValueError(short_url or "TinyURL returned an invalid response")
        return jsonify({"ok": True, "url": short_url})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "url": url}), 502

# ============================================================ Resume uploads
@app.route("/api/resumes", methods=["GET"])
def get_resumes():
    """Return the latest uploaded resume for each supported role."""
    return jsonify({"resumes": resume_payload()})

@app.route("/api/resumes/upload", methods=["POST"])
def upload_resume():
    """Upload a PDF resume and return the saved server path."""
    role = request.form.get("role", "fullstack")
    if role not in {"fullstack", "frontend"}:
        return jsonify({"ok": False, "error": "role must be fullstack or frontend"}), 400

    file = request.files.get("resume")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "resume file is required"}), 400

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".pdf"):
        return jsonify({"ok": False, "error": "only PDF resumes are supported"}), 400

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    save_path = UPLOAD_DIR / f"{role}_{timestamp}_{filename}"
    file.save(save_path)
    return jsonify({
        "ok": True,
        "resume": {
            "name": save_path.name,
            "path": str(save_path),
            "uploaded_at": datetime.fromtimestamp(save_path.stat().st_mtime).isoformat(),
        },
        "resumes": resume_payload(),
    })

# ============================================================ Bot status
@app.route("/api/status", methods=["GET"])
def get_status():
    """Get current bot status."""
    return jsonify(bot_status)

# ============================================================ Bot actions (in background threads)
def run_bot_action(action_name: str, **kwargs):
    """Run a bot action in background, update status."""
    def _worker():
        try:
            set_status("running", f"Running {action_name}...")
            cfg = load_config()

            if kwargs.get("gemini_key"):
                os.environ["GEMINI_API_KEY"] = kwargs["gemini_key"]
            if kwargs.get("gmail_user"):
                os.environ["GMAIL_USER"] = kwargs["gmail_user"]
            if kwargs.get("gmail_app_password"):
                os.environ["GMAIL_APP_PASSWORD"] = kwargs["gmail_app_password"]
            
            # Build resume paths
            resume_paths = {}
            if kwargs.get("resume_fullstack"):
                resume_paths["fullstack"] = kwargs["resume_fullstack"]
            if kwargs.get("resume_frontend"):
                resume_paths["frontend"] = kwargs["resume_frontend"]

            config_overrides = dict(kwargs.get("config_overrides", {}) or {})
            if kwargs.get("linkedin_email"):
                config_overrides["email"] = kwargs["linkedin_email"]
            if kwargs.get("linkedin_password"):
                config_overrides["password"] = kwargs["linkedin_password"]
            
            bot = LinkedInBot(
                headless=kwargs.get("headless", False),
                resume_paths=resume_paths if resume_paths else None,
                config_overrides=config_overrides
            )
            
            try:
                bot.login()
                
                if action_name == "stage1":
                    set_status("running", "Searching jobs...")
                    bot.start_applying()
                elif action_name == "stage2":
                    set_status("running", "Inviting recruiters...")
                    bot.populate_connections()
                elif action_name == "stage3":
                    set_status("running", "Extracting emails...")
                    bot.extract_emails()
                elif action_name == "search_posts":
                    set_status("running", "Searching posts...")
                    kw = kwargs.get("keywords", [])
                    max_per = kwargs.get("max_per_keyword", 20)
                    bot.search_recent_posts(
                        keywords=kw,
                        max_per_keyword=max_per,
                        recent_24_hours=kwargs.get("recent_24_hours", True),
                    )
                elif action_name == "send_emails_posts":
                    set_status("running", "Sending emails to post contacts...")
                    bot.send_emails_for_posts(
                        subject_template=kwargs.get("subject_template"),
                        body_template=kwargs.get("body_template"),
                        dry_run=kwargs.get("dry_run", False),
                        only_unsent=kwargs.get("only_unsent", True)
                    )
            finally:
                bot.close()
            
            set_status("done", f"{action_name} completed", "Check Results tab")
        except Exception as e:
            set_status("error", f"{action_name} failed: {str(e)}")

    with bot_action_lock:
        if bot_status.get("state") == "running":
            return False
        set_status("running", f"Starting {action_name}...")
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return True

def _busy_response():
    return jsonify({
        "ok": False,
        "status": "busy",
        "error": f"Another action is already running: {bot_status.get('message', '')}",
    }), 409

@app.route("/api/bot/stage1", methods=["POST"])
def bot_stage1():
    """Run Stage 1: search jobs."""
    data = request.json or {}
    if not run_bot_action("stage1", **data):
        return _busy_response()
    return jsonify({"ok": True, "status": "started"})

@app.route("/api/bot/stage2", methods=["POST"])
def bot_stage2():
    """Run Stage 2: invite recruiters."""
    data = request.json or {}
    if not run_bot_action("stage2", **data):
        return _busy_response()
    return jsonify({"ok": True, "status": "started"})

@app.route("/api/bot/stage3", methods=["POST"])
def bot_stage3():
    """Run Stage 3: extract emails."""
    data = request.json or {}
    if not run_bot_action("stage3", **data):
        return _busy_response()
    return jsonify({"ok": True, "status": "started"})

@app.route("/api/bot/search-posts", methods=["POST"])
def bot_search_posts():
    """Search LinkedIn posts by keywords."""
    data = request.json or {}
    kw = data.get("keywords", [])
    max_per = data.get("max_per_keyword", 20)
    payload = dict(data)
    payload.pop("keywords", None)
    payload.pop("max_per_keyword", None)
    if not run_bot_action("search_posts", keywords=kw, max_per_keyword=max_per, **payload):
        return _busy_response()
    return jsonify({"ok": True, "status": "started"})

@app.route("/api/bot/send-emails-posts", methods=["POST"])
def bot_send_emails_posts():
    """Send emails to collected post contacts."""
    data = request.json or {}
    if not run_bot_action("send_emails_posts", **data):
        return _busy_response()
    return jsonify({"ok": True, "status": "started"})

# ============================================================ Results
def _read_csv_safe(path):
    """Read a results CSV into a list of records, tolerating a missing or
    empty file (an empty DataFrame written for a 0-result run)."""
    if not path.exists():
        return 0, []
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return 0, []
    df = df.where(pd.notna(df), None)  # JSON-safe: NaN -> null
    return len(df), df.to_dict(orient="records")[:100]

@app.route("/api/results/jobs", methods=["GET"])
def get_jobs():
    """Fetch jobs.csv."""
    count, data = _read_csv_safe(OUTPUT_DIR / "jobs.csv")
    return jsonify({"count": count, "data": data})

@app.route("/api/results/connections", methods=["GET"])
def get_connections():
    """Fetch connections.csv."""
    count, data = _read_csv_safe(OUTPUT_DIR / "connections.csv")
    return jsonify({"count": count, "data": data})

@app.route("/api/results/posts", methods=["GET"])
def get_posts():
    """Fetch posts_emails.csv."""
    count, data = _read_csv_safe(OUTPUT_DIR / "posts_emails.csv")
    return jsonify({"count": count, "data": data})

@app.route("/api/results/clear", methods=["POST"])
def clear_results():
    """Clear all result CSVs."""
    for p in (OUTPUT_DIR / "jobs.csv", OUTPUT_DIR / "connections.csv", OUTPUT_DIR / "posts_emails.csv"):
        if p.exists():
            p.unlink()
    return jsonify({"ok": True})

# ============================================================ Health
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "version": "1.0"})

if __name__ == "__main__":
    # Port 5000 is hijacked by macOS AirPlay Receiver (Control Center), so
    # default to 5001. Override with PORT if needed.
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, port=port)
