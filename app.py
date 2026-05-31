"""Streamlit UI for the LinkedIn referral bot.

Run with: `streamlit run app.py`
"""
from __future__ import annotations

import io
import os
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from linkedinBot.utils.ai import (
    DEFAULT_AI_SYSTEM_PROMPT_TEMPLATE,
    DEFAULT_CANDIDATE_BIO_FRONTEND,
    DEFAULT_CANDIDATE_BIO_FULLSTACK,
    DEFAULT_CANDIDATE_EMAIL,
    DEFAULT_CANDIDATE_FIRST_NAME,
    DEFAULT_CANDIDATE_NAME,
    DEFAULT_CANDIDATE_PITCH,
    DEFAULT_CANDIDATE_PROFILE_BLOCK,
    DEFAULT_EMAIL_BODY_TEMPLATE,
    DEFAULT_EMAIL_SUBJECT_TEMPLATE,
    DEFAULT_INVITE_NOTE_TEMPLATE,
    DEFAULT_INVITE_NOTE_TEMPLATE_FRONTEND,
    DEFAULT_INVITE_NOTE_TEMPLATE_HIRER,
    DEFAULT_INVITE_NOTE_TEMPLATE_HIRER_FRONTEND,
    DEFAULT_RESUME_DRIVE_LINK,
    INVITE_NOTE_MAX,
    build_invite_note,
)
from linkedinBot.utils.shortlink import shorten as shorten_url
from linkedinBot.utils.mailer import GmailCreds, send_to_recruiters

DEFAULT_SINGLE_INVITE_NOTE = """Hi {name}, I came across the {job_title} opening at your company and believe my experience aligns well with the role.
I'd love to connect. Resume: {drive_link}"""

CONFIG_PATH = PROJECT_ROOT / "linkedinBot" / "configs" / "config.yaml"
OUTPUT_DIR = PROJECT_ROOT / "linkedinBot" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
JOBS_CSV = OUTPUT_DIR / "jobs.csv"
CONNECTIONS_CSV = OUTPUT_DIR / "connections.csv"
UPLOAD_DIR = PROJECT_ROOT / "linkedinBot" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- helpers
def load_yaml() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def save_yaml(data: dict) -> None:
    with CONFIG_PATH.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def df_to_xlsx_bytes(frames: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet, df in frames.items():
            (df if not df.empty else pd.DataFrame({"empty": []})).to_excel(
                writer, sheet_name=sheet[:31], index=False
            )
    return buf.getvalue()


def safe_read_csv(path: Path) -> pd.DataFrame:
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def run_in_thread(target, *args, **kwargs):
    def _runner():
        try:
            target(*args, **kwargs)
            st.session_state["bot_status"] = "done"
        except Exception as e:  # noqa: BLE001
            st.session_state["bot_status"] = "error"
            st.session_state["bot_error"] = str(e)

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    st.session_state["bot_status"] = "running"


# ---------------------------------------------------------------- page
st.set_page_config(page_title="LinkedIn Referral Bot", layout="wide")
st.title("LinkedIn Referral Bot")
st.caption("Hirer → recruiters → emails. Resume routing (fullstack vs frontend) + invite notes.")

cfg = load_yaml()
settings = cfg.setdefault("settings", {})
prefs = cfg.setdefault("jobPreferences", {})
candidate = cfg.setdefault("candidate", {})
your_name = candidate.get("name", DEFAULT_CANDIDATE_NAME)
your_first_name = candidate.get("first_name", DEFAULT_CANDIDATE_FIRST_NAME)
your_email = candidate.get("email", DEFAULT_CANDIDATE_EMAIL)


# =============================================================== sidebar
with st.sidebar:
    st.header("LinkedIn login")
    linkedin_email = st.text_input(
        "LinkedIn ID or email",
        value=os.environ.get("LINKEDIN_EMAIL", candidate.get("email", "")),
    )
    linkedin_password = st.text_input(
        "LinkedIn password",
        type="password",
        value=os.environ.get("LINKEDIN_PASSWORD", ""),
    )

    st.divider()
    st.header("Gemini")
    gemini_key = st.text_input(
        "Gemini API key",
        type="password",
        value=os.environ.get("GEMINI_API_KEY", ""),
    )

    st.divider()
    with st.expander("Gmail (for sending emails to recruiters)"):
        st.caption(
            "Create an App Password at "
            "Required only when you click 'Send emails' in the Email tab."
        )
        gmail_user = st.text_input("Gmail address", value=os.environ.get("GMAIL_USER") or your_email)
        gmail_app_password = st.text_input(
            "Gmail App Password (16 chars)",
            type="password",
            value=os.environ.get("GMAIL_APP_PASSWORD", ""),
        )

    st.divider()
    st.header("Resume")
    uploaded_fs = st.file_uploader("Resume PDF", type=["pdf"], key="resume_fs")
    if uploaded_fs:
        p = UPLOAD_DIR / "resume_fullstack.pdf"
        p.write_bytes(uploaded_fs.getvalue())
        st.session_state["resume_path_fullstack"] = str(p)
        st.success(f"Saved → {p.name}")
    else:
        default = PROJECT_ROOT / "resume_fullstack.pdf"
        if default.exists():
            st.session_state.setdefault("resume_path_fullstack", str(default))
            st.caption(f"Default: `{default.name}`")

    st.markdown("**Drive link** (auto-shortened for invite notes)")
    resume_drive_link = st.text_input(
        "Drive resume link",
        value=settings.get("resumeDriveLink", DEFAULT_RESUME_DRIVE_LINK),
        key="dlink_fs",
    )
    resume_drive_link_frontend = resume_drive_link
    if st.button("Shorten drive link via TinyURL"):
        with st.spinner("Shortening…"):
            s1 = shorten_url(resume_drive_link) if resume_drive_link else ""
        settings["resumeDriveLink"] = s1 or resume_drive_link
        settings["resumeDriveLinkFrontend"] = settings["resumeDriveLink"]
        save_yaml(cfg)
        st.success(settings["resumeDriveLink"])
        st.rerun()


# ================================================================ tabs
tab_setup, tab_notes, tab_run, tab_posts, tab_results, tab_email = st.tabs([
    "Setup",
    "Invite Note",
    "Run",
    "Posts",
    "Results",
    "Email recruiters",
])

# ---------------------------------------------------------------- Setup
with tab_setup:
    st.subheader("Job & connection preferences")
    col1, col2 = st.columns(2)
    with col1:
        positions = st.text_area(
            "Positions to search (one per line)",
            value="\n".join(prefs.get("positions", [])),
            height=180,
        ).strip().splitlines()
    with col2:
        recruiter_keywords = st.text_area(
            "Recruiter headline keywords (one per line)",
            value="\n".join(prefs.get("recruiterKeywords", [])),
            height=180,
        ).strip().splitlines()

    st.subheader("Bot toggles")
    s1, s2, s3 = st.columns(3)
    with s1:
        max_job_page = st.number_input("Max job pages per position", 1, 20, settings.get("maxJobPage", 5))
    with s2:
        max_people = st.number_input("Max recruiters per job", 1, 10, settings.get("maxPeoplePerProfile", 3))
    with s3:
        headless = st.checkbox("Run Chrome headless", value=False)

    s4, s5, s6 = st.columns(3)
    with s4:
        recruiters_only = st.checkbox(
            "Only message recruiters / hiring tagged profiles",
            value=settings.get("recruitersOnly", True),
        )
    with s5:
        send_invite_note = st.checkbox(
            "Attach personalised note to each invite",
            value=True,
            disabled=True,
        )
    with s6:
        contact_hirer_first = st.checkbox(
            "Send first invite to the hirer (the person who posted)",
            value=settings.get("contactHirerFirst", True),
        )

    if st.button("Save preferences", type="primary"):
        settings.update({
            "maxJobPage": int(max_job_page),
            "maxPeoplePerProfile": int(max_people),
            "recruitersOnly": bool(recruiters_only),
            "sendInviteNote": True,
            "contactHirerFirst": bool(contact_hirer_first),
            "resumeDriveLink": resume_drive_link,
            "resumeDriveLinkFrontend": resume_drive_link_frontend,
        })
        prefs.update({
            "positions": [p for p in positions if p],
            "recruiterKeywords": [k for k in recruiter_keywords if k],
        })
        save_yaml(cfg)
        st.success("Saved.")


# ---------------------------------------------------------------- Notes
with tab_notes:
    st.subheader("Invite note")
    st.caption(f"Placeholders: `{{name}}`, `{{job_title}}`, `{{company}}`, `{{drive_link}}`. LinkedIn cap: **{INVITE_NOTE_MAX}** chars.")

    tmpl_fs = st.text_area(
        "Connection invite message",
        value=settings.get("inviteNoteTemplate", DEFAULT_SINGLE_INVITE_NOTE),
        height=150,
    )
    p = build_invite_note(
        template=tmpl_fs,
        name="Priya Sharma",
        job_title="Senior Full Stack Developer",
        company="Acme Corp",
        job_link="https://www.linkedin.com/jobs/view/4192384726/",
        resume_link=resume_drive_link,
        candidate_first_name=your_first_name,
        candidate_bio=candidate.get("bio_fullstack", DEFAULT_CANDIDATE_BIO_FULLSTACK),
    )
    st.code(p, language="text")
    st.caption(f"Length: {len(p)} / {INVITE_NOTE_MAX}")

    if st.button("Save invite note"):
        settings.update({
            "inviteNoteTemplate": tmpl_fs,
            "inviteNoteTemplateFrontend": tmpl_fs,
            "inviteNoteTemplateHirer": tmpl_fs,
            "inviteNoteTemplateHirerFrontend": tmpl_fs,
            "sendInviteNote": True,
        })
        save_yaml(cfg)
        st.success("Saved.")


# ---------------------------------------------------------------- Run
with tab_run:
    st.subheader("Run the bot")
    st.caption(
        "**Stage 1** — find matching jobs. "
        "**Stage 2** — invite the hirer + recruiters per job. "
        "**Stage 3** — visit accepted profiles and scrape emails. "
        "**Stage 4** — send emails via Gmail."
    )

    if not (st.session_state.get("resume_path_fullstack") or st.session_state.get("resume_path_frontend")):
        st.warning("Upload at least one resume PDF in the sidebar.")
    if not (linkedin_email and linkedin_password and gemini_key):
        st.warning("Fill in LinkedIn credentials and Gemini API key in the sidebar.")

    c1, c2, c3, c4 = st.columns(4)
    btn_s1 = c1.button("Stage 1 — Jobs", use_container_width=True)
    btn_s2 = c2.button("Stage 2 — Invites", use_container_width=True)
    btn_s3 = c3.button("Stage 3 — Emails", use_container_width=True)
    btn_all = c4.button("Stages 1 → 2", type="primary", use_container_width=True)

    def _launch(stages: list[str]):
        os.environ["LINKEDIN_EMAIL"] = linkedin_email or ""
        os.environ["LINKEDIN_PASSWORD"] = linkedin_password or ""
        os.environ["GEMINI_API_KEY"] = gemini_key or ""
        if gmail_user:
            os.environ["GMAIL_USER"] = gmail_user
        if gmail_app_password:
            os.environ["GMAIL_APP_PASSWORD"] = gmail_app_password

        # Persist UI state to YAML before bot reads it.
        candidate.update({
            "name": your_name, "first_name": your_first_name, "email": your_email,
            "bio_fullstack": bio_fs if "bio_fs" in locals() else candidate.get("bio_fullstack"),
            "bio_frontend": bio_fe if "bio_fe" in locals() else candidate.get("bio_frontend"),
            "pitch": pitch if "pitch" in locals() else candidate.get("pitch"),
            "profile_block": profile_block if "profile_block" in locals() else candidate.get("profile_block"),
        })
        settings.update({
            "maxJobPage": int(max_job_page) if "max_job_page" in locals() else settings.get("maxJobPage", 5),
            "maxPeoplePerProfile": int(max_people) if "max_people" in locals() else settings.get("maxPeoplePerProfile", 3),
            "recruitersOnly": bool(recruiters_only) if "recruiters_only" in locals() else settings.get("recruitersOnly", True),
            "sendInviteNote": bool(send_invite_note) if "send_invite_note" in locals() else settings.get("sendInviteNote", True),
            "contactHirerFirst": bool(contact_hirer_first) if "contact_hirer_first" in locals() else settings.get("contactHirerFirst", True),
            "resumeDriveLink": resume_drive_link,
            "resumeDriveLinkFrontend": resume_drive_link_frontend,
        })
        save_yaml(cfg)

        from linkedinBot.bot import LinkedInBot

        resume_paths = {k: v for k, v in {
            "fullstack": st.session_state.get("resume_path_fullstack"),
            "frontend": st.session_state.get("resume_path_frontend"),
        }.items() if v}

        def _job():
            bot = LinkedInBot(headless=headless, resume_paths=resume_paths)
            try:
                bot.login()
                if "s1" in stages:
                    bot.start_applying()
                if "s2" in stages:
                    bot.populate_connections()
                if "s3" in stages:
                    bot.extract_emails()
            finally:
                bot.close()

        run_in_thread(_job)

    if btn_s1: _launch(["s1"])
    if btn_s2: _launch(["s2"])
    if btn_s3: _launch(["s3"])
    if btn_all: _launch(["s1", "s2"])

    status = st.session_state.get("bot_status")
    if status == "running":
        st.info("Bot is running — watch the Chrome window. Refresh to update.")
        if st.button("Refresh"):
            st.rerun()
    elif status == "done":
        st.success("Bot finished. Check Results tab.")
    elif status == "error":
        st.error(f"Bot errored: {st.session_state.get('bot_error', 'unknown')}")


# ---------------------------------------------------------------- Results
with tab_results:
    df_jobs = safe_read_csv(JOBS_CSV)
    df_conn = safe_read_csv(CONNECTIONS_CSV)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Jobs matched", len(df_jobs))
    m2.metric("Profiles touched", len(df_conn))
    m3.metric(
        "Emails collected",
        int(df_conn["email"].astype(str).str.contains("@", na=False).sum()) if "email" in df_conn.columns else 0,
    )
    m4.metric(
        "Emails sent",
        int(df_conn["email_sent"].fillna(False).astype(bool).sum()) if "email_sent" in df_conn.columns else 0,
    )

    st.markdown("### Jobs")
    if df_jobs.empty:
        st.info("No jobs yet — run Stage 1.")
    else:
        st.dataframe(df_jobs, use_container_width=True, height=300)

    st.markdown("### Recruiters / hirers")
    if df_conn.empty:
        st.info("No connections yet — run Stage 2.")
    else:
        st.dataframe(df_conn, use_container_width=True, height=340)

    st.divider()
    st.markdown("### Download")
    if df_jobs.empty and df_conn.empty:
        st.caption("Nothing to download yet.")
    else:
        st.download_button(
            "Download Excel (jobs + connections)",
            data=df_to_xlsx_bytes({"jobs": df_jobs, "connections": df_conn}),
            file_name=f"linkedin_referrals_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

    if st.button("Clear all collected data"):
        for p in (JOBS_CSV, CONNECTIONS_CSV):
            if p.exists():
                p.unlink()
        st.success("Cleared. Refresh to update.")


# ---------------------------------------------------------------- Posts
with tab_posts:
    st.subheader("Search recent LinkedIn posts & outreach")
    st.caption("Search public LinkedIn posts by keyword, collect emails found, and optionally send outreach.")

    cfg_posts = settings.get("postSearch", {})
    kw_default = ",".join(cfg_posts.get("keywords", []))
    kw_text = st.text_area("Keywords (comma-separated)", value=kw_default, height=80)
    max_per = st.number_input("Best-match posts to review", 20, 50, min(max(cfg_posts.get("maxPostsPerKeyword", 20), 20), 50))
    recent_24_hours = st.checkbox("Only recent posts from the last 24 hours", value=cfg_posts.get("recent24Hours", True))

    c1, c2 = st.columns(2)
    if c1.button("Search posts"):
        # persist settings + creds like Run tab
        os.environ["LINKEDIN_EMAIL"] = linkedin_email or ""
        os.environ["LINKEDIN_PASSWORD"] = linkedin_password or ""
        if gmail_user:
            os.environ["GMAIL_USER"] = gmail_user
        if gmail_app_password:
            os.environ["GMAIL_APP_PASSWORD"] = gmail_app_password

        # save config
        settings.setdefault("postSearch", {})
        settings["postSearch"]["keywords"] = [k.strip() for k in kw_text.split(",") if k.strip()]
        settings["postSearch"]["maxPostsPerKeyword"] = int(max_per)
        settings["postSearch"]["recent24Hours"] = bool(recent_24_hours)
        save_yaml(cfg)

        from linkedinBot.bot import LinkedInBot

        resume_paths = {k: v for k, v in {
            "fullstack": st.session_state.get("resume_path_fullstack"),
            "frontend": st.session_state.get("resume_path_frontend"),
        }.items() if v}

        def _search():
            bot = LinkedInBot(headless=headless, resume_paths=resume_paths)
            try:
                bot.login()
                bot.search_recent_posts(
                    keywords=settings["postSearch"]["keywords"],
                    max_per_keyword=int(max_per),
                    recent_24_hours=bool(recent_24_hours),
                )
            finally:
                bot.close()

        run_in_thread(_search)

    posts_csv_path = OUTPUT_DIR / "posts_emails.csv"
    df_posts = safe_read_csv(posts_csv_path)
    st.markdown("### Collected posts & emails")
    if df_posts.empty:
        st.info("No posts collected yet — run a search.")
    else:
        st.dataframe(df_posts, use_container_width=True, height=300)
        st.download_button("Download CSV", data=df_posts.to_csv(index=False), file_name="posts_emails.csv")

    st.divider()
    st.subheader("Send outreach to discovered emails")
    subj_p = st.text_input("Email subject template", value=settings.get("emailSubjectTemplate") or DEFAULT_EMAIL_SUBJECT_TEMPLATE)
    body_p = st.text_area("Email body template", value=settings.get("emailBodyTemplate") or DEFAULT_EMAIL_BODY_TEMPLATE, height=220)
    dry_run_posts = st.checkbox("Dry run (don't actually send)", value=True)

    sp, ss = st.columns(2)
    if sp.button("Dry run (preview) for posts"):
        os.environ["GMAIL_USER"] = gmail_user or ""
        os.environ["GMAIL_APP_PASSWORD"] = gmail_app_password or ""

        from linkedinBot.bot import LinkedInBot

        def _dry():
            bot = LinkedInBot(headless=headless, resume_paths={})
            try:
                bot.send_emails_for_posts(subject_template=subj_p, body_template=body_p, dry_run=True, only_unsent=True)
            finally:
                bot.close()

        run_in_thread(_dry)

    if ss.button("Send emails now (posts)"):
        if not (gmail_user and gmail_app_password):
            st.error("Gmail credentials missing — open the Gmail expander in the sidebar.")
        else:
            os.environ["GMAIL_USER"] = gmail_user
            os.environ["GMAIL_APP_PASSWORD"] = gmail_app_password

            from linkedinBot.bot import LinkedInBot

            def _send():
                bot = LinkedInBot(headless=headless, resume_paths={})
                try:
                    bot.send_emails_for_posts(subject_template=subj_p, body_template=body_p, dry_run=False, only_unsent=True)
                finally:
                    bot.close()

            run_in_thread(_send)


# ---------------------------------------------------------------- Email tab
with tab_email:
    st.subheader("Send personalised emails to recruiters")
    st.caption(
        "Uses Gmail SMTP. Set your Gmail App Password in the sidebar first. "
        "Recipient pool = rows in connections.csv with an email."
    )

    df = safe_read_csv(CONNECTIONS_CSV)
    if df.empty:
        st.info("No connections yet — run Stages 2 then 3 first.")
    else:
        eligible = df[df["email"].astype(str).str.contains("@", na=False)] if "email" in df.columns else df.head(0)
        if "email_sent" in eligible.columns:
            eligible["email_sent"] = eligible["email_sent"].fillna(False).astype(bool)
            unsent = eligible[~eligible["email_sent"]]
        else:
            unsent = eligible

        st.write(
            f"**{len(eligible)} recruiters with an email** "
            f"({len(unsent)} unsent)."
        )

        subj = st.text_input(
            "Email subject template",
            value=settings.get("emailSubjectTemplate") or DEFAULT_EMAIL_SUBJECT_TEMPLATE,
        )
        body = st.text_area(
            "Email body template",
            value=settings.get("emailBodyTemplate") or DEFAULT_EMAIL_BODY_TEMPLATE,
            height=260,
        )
        st.caption(
            "Placeholders: `{name}` `{job_title}` `{company}` `{candidate_name}` "
            "`{candidate_first_name}` `{candidate_email}` `{candidate_bio_long}` `{resume_link}`."
        )

        sample = eligible.head(1)
        if not sample.empty:
            r = sample.iloc[0]
            ctx = {
                "name": str(r.get("profile_name") or "there").split()[0],
                "job_title": r.get("job_title") or "this role",
                "company": r.get("company_name") or "your company",
                "candidate_name": your_name,
                "candidate_first_name": your_first_name,
                "candidate_email": your_email,
                "candidate_bio_long": pitch if "pitch" in locals() else candidate.get("pitch", ""),
                "resume_link": resume_drive_link,
            }
            try:
                preview_subj = subj.format(**ctx)
                preview_body = body.format(**ctx)
            except KeyError as e:
                preview_subj = f"(template error: missing {e})"
                preview_body = ""
            st.markdown("**Preview (first recruiter):**")
            st.code(f"To: {r.get('email')}\nSubject: {preview_subj}\n\n{preview_body}", language="text")

        col_a, col_b, col_c = st.columns(3)
        if col_a.button("Save email templates"):
            settings["emailSubjectTemplate"] = subj
            settings["emailBodyTemplate"] = body
            save_yaml(cfg)
            st.success("Saved.")

        if col_b.button("Dry run (preview all, send none)"):
            creds = GmailCreds(user=gmail_user or "x@x", app_password=gmail_app_password or "x")
            res = send_to_recruiters(
                str(CONNECTIONS_CSV), subj, body, creds,
                candidate_ctx={
                    "candidate_name": your_name,
                    "candidate_first_name": your_first_name,
                    "candidate_email": your_email,
                    "candidate_bio_long": pitch if "pitch" in locals() else candidate.get("pitch", ""),
                    "resume_link": resume_drive_link,
                },
                dry_run=True,
            )
            st.info(f"Dry run: would send {res['sent']} emails, skip {res['skipped']}.")

        if col_c.button("Send emails now", type="primary"):
            if not (gmail_user and gmail_app_password):
                st.error("Gmail credentials missing — open the Gmail expander in the sidebar.")
            else:
                creds = GmailCreds(user=gmail_user, app_password=gmail_app_password)
                with st.spinner("Sending…"):
                    res = send_to_recruiters(
                        str(CONNECTIONS_CSV), subj, body, creds,
                        candidate_ctx={
                            "candidate_name": your_name,
                            "candidate_first_name": your_first_name,
                            "candidate_email": your_email,
                            "candidate_bio_long": pitch if "pitch" in locals() else candidate.get("pitch", ""),
                            "resume_link": resume_drive_link,
                        },
                    )
                if res["failed"]:
                    st.warning(f"Sent {res['sent']}, failed {res['failed']}, skipped {res['skipped']}.")
                else:
                    st.success(f"Sent {res['sent']} emails (skipped {res['skipped']}).")

        st.markdown("### Recipient list (with emails)")
        st.dataframe(eligible, use_container_width=True, height=340)
