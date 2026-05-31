"""Light CLI wrapper to run the LinkedIn bot with environment-variable overrides.

Usage:
  - Copy `.env.example` to `.env` (optional) and export variables, or set env vars directly.
  - Run: `python run_bot.py`

This script reads `linkedinBot/configs/config.yaml` by default and applies simple
overrides from environment variables so the bot can run outside the Streamlit UI.
"""
from __future__ import annotations

import os
import yaml
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", PROJECT_ROOT / "linkedinBot" / "configs" / "config.yaml"))

# Map a small set of ENV vars to the bot's config keys. Add more as needed.
ENV_TO_CONFIG = {
    "POSITIONS": ("positions", lambda v: [p.strip() for p in v.split(",") if p.strip()]),
    "PEOPLE_PROFILES": ("people_profiles", lambda v: [p.strip() for p in v.split(",") if p.strip()]),
    "RECRUITER_KEYWORDS": ("recruiterKeywords", lambda v: [p.strip().lower() for p in v.split(",") if p.strip()]),
    "MAX_JOB_PAGE": ("maxJobPage", int),
    "MAX_PEOPLE_PER_PROFILE": ("maxPeoplePerProfile", int),
    "RECRUITERS_ONLY": ("recruitersOnly", lambda v: v.lower() in ("1", "true", "yes", "y")),
    "SEND_INVITE_NOTE": ("sendInviteNote", lambda v: v.lower() in ("1", "true", "yes", "y")),
    "CONTACT_HIRER_FIRST": ("contactHirerFirst", lambda v: v.lower() in ("1", "true", "yes", "y")),
    "AI_SYSTEM_PROMPT": ("aiSystemPromptTemplate", str),
    "RESUME_LINK": ("resumeDriveLink", str),
    "RESUME_LINK_FRONTEND": ("resumeDriveLinkFrontend", str),
}

# Candidate-specific env vars
CANDIDATE_ENVS = {
    "CANDIDATE_NAME": "candidateName",
    "CANDIDATE_FIRST_NAME": "candidateFirstName",
    "CANDIDATE_EMAIL": "candidateEmail",
    "CANDIDATE_BIO_FS": "candidateBioFullstack",
    "CANDIDATE_BIO_FE": "candidateBioFrontend",
    "CANDIDATE_PITCH": "candidatePitch",
}

if __name__ == "__main__":
    print("Loading config:", CONFIG_PATH)
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        cfg = {}

    settings = cfg.setdefault("settings", {})
    prefs = cfg.setdefault("jobPreferences", {})
    candidate = cfg.setdefault("candidate", {})

    overrides = {}
    for env, (key, caster) in ENV_TO_CONFIG.items():
        v = os.environ.get(env)
        if v is not None and v != "":
            overrides[key] = caster(v)

    # Candidate overrides
    for env, key in CANDIDATE_ENVS.items():
        v = os.environ.get(env)
        if v is not None and v != "":
            overrides[key] = v

    # Resume file paths (local PDFs). These will be passed as resume_paths to LinkedInBot.
    resume_paths = {}
    fs = os.environ.get("RESUME_PATH_FULLSTACK")
    fe = os.environ.get("RESUME_PATH_FRONTEND")
    if fs:
        resume_paths["fullstack"] = fs
    if fe:
        resume_paths["frontend"] = fe

    headless = os.environ.get("HEADLESS", "0") in ("1", "true", "yes", "y")

    # Import here so the module-level code in linkedinBot can resolve PROJECT_ROOT properly.
    from linkedinBot.bot import LinkedInBot

    print("Starting bot with overrides:", overrides)
    bot = LinkedInBot(headless=headless, resume_paths=resume_paths or None, config_overrides=overrides)

    try:
        bot.login()
        # Default run: Stage 1 (start_applying) then Stage 2 (populate_connections) then extract emails.
        bot.start_applying()
        time.sleep(1)
        bot.populate_connections()
        time.sleep(1)
        bot.extract_emails()
    finally:
        bot.close()

    print("Done.")
