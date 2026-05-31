# LinkedIn Referral Bot — Mohnish

Automates LinkedIn referral outreach: searches matching jobs, AI-matches each against your resume, then visits the hiring company's **People** page, finds **recruiters / talent-acquisition profiles**, and sends a personalised connection invite that includes the specific job link and a link to your resume on Google Drive.

A Streamlit UI on top lets you upload a resume, tweak the invite-note template, pick which connections to message, and download the final results as Excel.

## Features

- **AI job matching** against your resume (Gemini) — only saves jobs that fit.
- **Recruiter-only outreach** — filters company people by headline (`Recruiter`, `Talent Acquisition`, `Hiring`, …).
- **Personalised invite note** with the actual job link and your resume Drive link (auto-trimmed to LinkedIn's 300-char cap).
- **Email extraction** from any visible profile text via regex.
- **Streamlit UI** — upload resume, edit note template (live char-count + preview), toggle settings, view tables, download `.xlsx`.

## Quickstart

```bash
# 1) Install deps (Python 3.10+ recommended)
pip install -r linkedinBot/requirements.txt

# 2) Set env vars (or paste them into the sidebar of the UI)
export LINKEDIN_EMAIL="you@example.com"
export LINKEDIN_PASSWORD="..."
export GEMINI_API_KEY="..."

# 3) Launch the UI
streamlit run app.py
```

Then in the UI:

1. **Sidebar** → upload your resume PDF + paste credentials.
2. **Setup tab** → tweak positions, recruiter keywords, max jobs/recruiters, recruiter-only toggle.
3. **Note Template tab** → edit the invite note (placeholders: `{name} {job_title} {company} {job_link} {resume_link}`) and watch the live character count.
4. **Run Bot tab** → click **Stage 1** to collect matching jobs, then **Stage 2** to connect with recruiters per job. Or **Run Both**.
5. **Results tab** → preview the jobs/connections tables and **download Excel**.

## Default invite note template

```
Hi {name}, I'm Mohnish — Full Stack Dev (4+ yrs, React/Node/Python). Saw the {job_title} role: {job_link}. I think I'm a strong fit and would really appreciate a referral. Resume: {resume_link}
```

## Project layout

```
linkdinbot/
├── app.py                          # Streamlit UI
├── Mohnish_Resume_Full_Stack_Developer.pdf
└── linkedinBot/
    ├── bot.py                      # Selenium driver, job search, recruiter outreach
    ├── configs/config.yaml         # Persisted preferences (edited from the UI)
    ├── output/
    │   ├── jobs.csv                # Stage 1 output
    │   └── connections.csv         # Stage 2 output
    ├── uploads/                    # Resume uploads from the UI
    └── utils/
        ├── ai.py                   # Gemini job-match + invite-note builder
        └── gsheet.py               # Optional Google Sheets export
```

## Notes & caveats

- **Free LinkedIn accounts get ~5 invites with a note per month.** If you hit the cap, turn **"Attach personalised note"** off in the Run tab — the bot will fall back to invites without a note.
- **Weekly invitation limit** — LinkedIn caps total weekly invites (~100). The bot detects this and stops gracefully.
- **Email extraction is best-effort** — only works when a recruiter writes their email into their headline / About section. LinkedIn does not expose 1st-degree email until after they accept the invite.
- **Headless mode** is supported but LinkedIn aggressively challenges headless logins; run with a visible browser the first time.

## Configuration & running outside the UI

- Copy `.env.example` to `.env` and fill or export the environment variables you need.
- A lightweight runner `run_bot.py` reads `linkedinBot/configs/config.yaml` by default and applies simple overrides from environment variables (see `.env.example`).
- Run from the repo root:

```bash
python run_bot.py
```

- To push this repo to your GitHub, use the helper script `scripts/push_to_github.sh`.
    Provide a remote URL as the first arg or set `GIT_REMOTE` in your environment:

```bash
./scripts/push_to_github.sh git@github.com:youruser/yourrepo.git main
```

## Disclaimer

For personal job-seeking use. Respect LinkedIn's terms of service and connection limits — use the rate-limit toggles in `config.yaml`.
# linkdinbot
