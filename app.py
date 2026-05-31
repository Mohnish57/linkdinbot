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
st.set_page_config(page_title="LinkedIn Referral Bot", page_icon="🤖", layout="wide")
st.title("🤖 LinkedIn Referral Bot")
st.caption("Hirer → recruiters → emails. Resume routing (fullstack vs frontend) + invite notes.")

cfg = load_yaml()
settings = cfg.setdefault("settings", {})
prefs = cfg.setdefault("jobPreferences", {})
candidate = cfg.setdefault("candidate", {})


# =============================================================== sidebar
with st.sidebar:
    st.header("👤 You")
    your_name = st.text_input(
        "Your full name", value=candidate.get("name", DEFAULT_CANDIDATE_NAME)
    )
    your_first_name = st.text_input(
        "First name (used in invite notes)",
        value=candidate.get("first_name", DEFAULT_CANDIDATE_FIRST_NAME),
    )
    your_email = st.text_input(
        "Your contact email (FROM address for emails)",
        value=candidate.get("email", DEFAULT_CANDIDATE_EMAIL),
    )

    st.divider()
    st.header("🔑 LinkedIn login")
    linkedin_email = st.text_input(
        "LinkedIn email",
        value=os.environ.get("LINKEDIN_EMAIL", candidate.get("email", "")),
    )
    linkedin_password = st.text_input(
        "LinkedIn password",
        type="password",
        value=os.environ.get("LINKEDIN_PASSWORD", ""),
    )

    st.divider()
    st.header("🤖 Gemini")
    gemini_key = st.text_input(
        "Gemini API key",
        type="password",
        value=os.environ.get("GEMINI_API_KEY", ""),
    )

    st.divider()
    with st.expander("📨 Gmail (for sending emails to recruiters)"):
        st.caption(
            "Create an App Password at "
            "[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). "
            "Required only when you click 'Send emails' in the Email tab."
        )
        gmail_user = st.text_input("Gmail address", value=os.environ.get("GMAIL_USER") or your_email)
        gmail_app_password = st.text_input(
            "Gmail App Password (16 chars)",
            type="password",
            value=os.environ.get("GMAIL_APP_PASSWORD", ""),
        )

    st.divider()
    st.header("📄 Resumes")
    uploaded_fs = st.file_uploader("Full Stack resume PDF", type=["pdf"], key="resume_fs")
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

    uploaded_fe = st.file_uploader("Frontend resume PDF", type=["pdf"], key="resume_fe")
    if uploaded_fe:
        p = UPLOAD_DIR / "resume_frontend.pdf"
        p.write_bytes(uploaded_fe.getvalue())
        st.session_state["resume_path_frontend"] = str(p)
        st.success(f"Saved → {p.name}")
    else:
        default = PROJECT_ROOT / "resume_frontend.pdf"
        if default.exists():
            st.session_state.setdefault("resume_path_frontend", str(default))
            st.caption(f"Default: `{default.name}`")

    st.markdown("**Drive links** (auto-shortened for invite notes)")
    resume_drive_link = st.text_input(
        "Full Stack drive link",
        value=settings.get("resumeDriveLink", DEFAULT_RESUME_DRIVE_LINK),
        key="dlink_fs",
    )
    resume_drive_link_frontend = st.text_input(
        "Frontend drive link",
        value=settings.get(
            "resumeDriveLinkFrontend", settings.get("resumeDriveLink", DEFAULT_RESUME_DRIVE_LINK)
        ),
        key="dlink_fe",
    )
    if st.button("🔗 Shorten both drive links via TinyURL"):
        with st.spinner("Shortening…"):
            s1 = shorten_url(resume_drive_link) if resume_drive_link else ""
            s2 = shorten_url(resume_drive_link_frontend) if resume_drive_link_frontend else ""
        settings["resumeDriveLink"] = s1 or resume_drive_link
        settings["resumeDriveLinkFrontend"] = s2 or resume_drive_link_frontend
        save_yaml(cfg)
        st.success(f"Full Stack: {settings['resumeDriveLink']}\nFrontend: {settings['resumeDriveLinkFrontend']}")
        st.rerun()


# ================================================================ tabs
tab_setup, tab_candidate, tab_notes, tab_ai, tab_run, tab_results, tab_email = st.tabs([
    "⚙️ Setup",
    "🪪 Candidate",
    "💬 Invite Notes",
    "🧠 AI Prompt",
    "▶️ Run",
    "📊 Results",
    "📨 Email recruiters",
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
        recruiter_keywords = st.text_area(
            "Recruiter headline keywords (one per line)",
            value="\n".join(prefs.get("recruiterKeywords", [])),
            height=140,
        ).strip().splitlines()
    with col2:
        people_profiles = st.text_area(
            "People-search keywords inside each company (one per line)",
            value="\n".join(prefs.get("people_profiles", [])),
            height=180,
        ).strip().splitlines()
        blacklisted_titles = st.text_area(
            "Blacklisted job titles (one per line)",
            value="\n".join(prefs.get("blacklistedTitles", [])),
            height=140,
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
            value=settings.get("sendInviteNote", True),
        )
    with s6:
        contact_hirer_first = st.checkbox(
            "Send first invite to the hirer (the person who posted)",
            value=settings.get("contactHirerFirst", True),
        )

    if st.button("💾 Save preferences", type="primary"):
        settings.update({
            "maxJobPage": int(max_job_page),
            "maxPeoplePerProfile": int(max_people),
            "recruitersOnly": bool(recruiters_only),
            "sendInviteNote": bool(send_invite_note),
            "contactHirerFirst": bool(contact_hirer_first),
            "resumeDriveLink": resume_drive_link,
            "resumeDriveLinkFrontend": resume_drive_link_frontend,
        })
        prefs.update({
            "positions": [p for p in positions if p],
            "people_profiles": [p for p in people_profiles if p],
            "recruiterKeywords": [k for k in recruiter_keywords if k],
            "blacklistedTitles": [t for t in blacklisted_titles if t],
        })
        save_yaml(cfg)
        st.success("Saved.")


# ---------------------------------------------------------------- Candidate
with tab_candidate:
    st.subheader("Candidate profile (used in invite notes + AI prompt + emails)")
    st.caption("Everything here is configurable — change once, reflected everywhere.")
    col_a, col_b = st.columns(2)
    with col_a:
        bio_fs = st.text_input(
            "Short bio — Full Stack (≤ 60 chars, used in invite notes)",
            value=candidate.get("bio_fullstack", DEFAULT_CANDIDATE_BIO_FULLSTACK),
        )
    with col_b:
        bio_fe = st.text_input(
            "Short bio — Frontend (≤ 60 chars)",
            value=candidate.get("bio_frontend", DEFAULT_CANDIDATE_BIO_FRONTEND),
        )

    pitch = st.text_area(
        "Long pitch (used in the post-connection follow-up DM Gemini generates)",
        value=candidate.get("pitch", DEFAULT_CANDIDATE_PITCH),
        height=110,
    )
    profile_block = st.text_area(
        "AI profile block (full bullet list, used in the AI prompt)",
        value=candidate.get("profile_block", DEFAULT_CANDIDATE_PROFILE_BLOCK),
        height=220,
    )

    if st.button("💾 Save candidate profile"):
        candidate.update({
            "name": your_name,
            "first_name": your_first_name,
            "email": your_email,
            "bio_fullstack": bio_fs,
            "bio_frontend": bio_fe,
            "pitch": pitch,
            "profile_block": profile_block,
        })
        save_yaml(cfg)
        st.success("Saved.")


# ---------------------------------------------------------------- Notes
with tab_notes:
    st.subheader("Invite note templates")
    st.caption(
        f"Placeholders: `{{name}}`, `{{job_title}}`, `{{company}}`, `{{resume_link}}`, "
        f"`{{candidate_first_name}}`, `{{candidate_bio}}`. "
        f"LinkedIn cap: **{INVITE_NOTE_MAX}** chars. "
        f"Bot picks Hirer template for the job-poster, otherwise Recruiter."
    )

    def preview(template, variant, is_hirer):
        return build_invite_note(
            template=template,
            name="Priya Sharma",
            job_title="Senior Full Stack Developer" if variant == "fullstack" else "Senior Frontend Developer",
            company="Acme Corp",
            job_link="https://www.linkedin.com/jobs/view/4192384726/",
            resume_link=resume_drive_link if variant == "fullstack" else resume_drive_link_frontend,
            candidate_first_name=your_first_name,
            candidate_bio=bio_fs if variant == "fullstack" else bio_fe,
        )

    # Row 1: recruiter templates
    st.markdown("##### Recruiter invites")
    c1, c2 = st.columns(2)
    with c1:
        tmpl_fs = st.text_area(
            "Recruiter — Full Stack",
            value=settings.get("inviteNoteTemplate", DEFAULT_INVITE_NOTE_TEMPLATE),
            height=150,
        )
        p = preview(tmpl_fs, "fullstack", False)
        st.code(p, language="text")
        st.caption(f"Length: {len(p)} / {INVITE_NOTE_MAX}")
    with c2:
        tmpl_fe = st.text_area(
            "Recruiter — Frontend",
            value=settings.get("inviteNoteTemplateFrontend", DEFAULT_INVITE_NOTE_TEMPLATE_FRONTEND),
            height=150,
        )
        p = preview(tmpl_fe, "frontend", False)
        st.code(p, language="text")
        st.caption(f"Length: {len(p)} / {INVITE_NOTE_MAX}")

    # Row 2: hirer templates
    st.markdown("##### Hirer (job poster) invites — sent FIRST per job")
    c3, c4 = st.columns(2)
    with c3:
        tmpl_h_fs = st.text_area(
            "Hirer — Full Stack",
            value=settings.get("inviteNoteTemplateHirer", DEFAULT_INVITE_NOTE_TEMPLATE_HIRER),
            height=150,
        )
        p = preview(tmpl_h_fs, "fullstack", True)
        st.code(p, language="text")
        st.caption(f"Length: {len(p)} / {INVITE_NOTE_MAX}")
    with c4:
        tmpl_h_fe = st.text_area(
            "Hirer — Frontend",
            value=settings.get("inviteNoteTemplateHirerFrontend", DEFAULT_INVITE_NOTE_TEMPLATE_HIRER_FRONTEND),
            height=150,
        )
        p = preview(tmpl_h_fe, "frontend", True)
        st.code(p, language="text")
        st.caption(f"Length: {len(p)} / {INVITE_NOTE_MAX}")

    if st.button("💾 Save all four note templates"):
        settings.update({
            "inviteNoteTemplate": tmpl_fs,
            "inviteNoteTemplateFrontend": tmpl_fe,
            "inviteNoteTemplateHirer": tmpl_h_fs,
            "inviteNoteTemplateHirerFrontend": tmpl_h_fe,
        })
        save_yaml(cfg)
        st.success("Saved.")


# ---------------------------------------------------------------- AI Prompt
with tab_ai:
    st.subheader("Gemini system prompt")
    st.caption(
        "Used when Gemini evaluates each job. Placeholders: "
        "`{candidate_name}`, `{candidate_profile_block}`, `{candidate_pitch}`, `{resume_link}`, `{candidate_email}`."
    )
    ai_prompt = st.text_area(
        "AI system prompt template",
        value=settings.get("aiSystemPromptTemplate", DEFAULT_AI_SYSTEM_PROMPT_TEMPLATE),
        height=420,
    )
    if st.button("💾 Save AI prompt"):
        settings["aiSystemPromptTemplate"] = ai_prompt
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
    btn_s1 = c1.button("🔍 Stage 1 — Jobs", use_container_width=True)
    btn_s2 = c2.button("🤝 Stage 2 — Invites", use_container_width=True)
    btn_s3 = c3.button("📇 Stage 3 — Emails", use_container_width=True)
    btn_all = c4.button("⚡ Stages 1 → 2", type="primary", use_container_width=True)

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
        if st.button("🔄 Refresh"):
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
            "⬇️ Download Excel (jobs + connections)",
            data=df_to_xlsx_bytes({"jobs": df_jobs, "connections": df_conn}),
            file_name=f"linkedin_referrals_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

    if st.button("🗑️ Clear all collected data"):
        for p in (JOBS_CSV, CONNECTIONS_CSV):
            if p.exists():
                p.unlink()
        st.success("Cleared. Refresh to update.")


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
            f"📇 **{len(eligible)} recruiters with an email** "
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
        if col_a.button("💾 Save email templates"):
            settings["emailSubjectTemplate"] = subj
            settings["emailBodyTemplate"] = body
            save_yaml(cfg)
            st.success("Saved.")

        if col_b.button("👀 Dry run (preview all, send none)"):
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

        if col_c.button("📨 Send emails NOW", type="primary"):
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
                    st.success(f"Sent {res['sent']} emails ✅ (skipped {res['skipped']}).")

        st.markdown("### Recipient list (with emails)")
        st.dataframe(eligible, use_container_width=True, height=340)
