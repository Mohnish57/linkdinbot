from __future__ import annotations

import os
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.utils import secure_filename


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "linkedinBot" / "configs" / "config.yaml"
UPLOAD_DIR = Path(tempfile.gettempdir()) / "linkdinbot_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
CORS(app)


def load_config():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def deep_merge(base: dict, updates: dict):
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


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


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "runtime": os.environ.get("RUNTIME", "python"), "version": "1.0"})


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
def update_config():
    cfg = deep_merge(load_config(), request.json or {})
    # Vercel's bundled filesystem is read-only. Return the merged config so the
    # UI updates immediately; persistent config changes belong in git/env.
    return jsonify({"ok": True, "config": cfg, "persistent": False})


@app.route("/api/shorten-url", methods=["POST"])
def shorten_url():
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


@app.route("/api/resumes", methods=["GET"])
def get_resumes():
    return jsonify({"resumes": resume_payload(), "persistent": False})


@app.route("/api/resumes/upload", methods=["POST"])
def upload_resume():
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
        "persistent": False,
        "resume": {
            "name": save_path.name,
            "path": str(save_path),
            "uploaded_at": datetime.fromtimestamp(save_path.stat().st_mtime).isoformat(),
        },
        "resumes": resume_payload(),
    })


@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({"state": "idle", "message": "Vercel API is online"})


@app.route("/api/results/<path:_name>", methods=["GET", "POST"])
def results_unavailable(_name):
    return jsonify({"count": 0, "data": [], "message": "Results require the worker backend."})


@app.route("/api/bot/<path:_action>", methods=["POST"])
def bot_unavailable(_action):
    return jsonify({
        "ok": False,
        "error": "Bot execution requires a persistent worker backend with Chrome/Selenium. Use Render, Railway, Fly.io, or a VPS for bot stages.",
    }), 501

