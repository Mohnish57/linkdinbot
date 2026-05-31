# LinkedIn Referral Bot

A configurable LinkedIn outreach automation tool that searches jobs, evaluates matches, connects with recruiters, and sends follow-up emails.

**Now with React UI + Flask API backend!** (Replaces Streamlit for better deployment flexibility)

## Features

- AI-assisted job matching and recruiter outreach
- LinkedIn post search + email discovery and outreach
- Configurable job searches, recruiter filters, invite templates, and email templates
- React web UI (deployable on Vercel)
- Flask API backend (deployable on Railway/Render/Heroku)
- Optional CLI runner for headless operation

## Quick start

See [SETUP.md](SETUP.md) for detailed setup instructions.

**TL;DR:**
```bash
# Terminal 1: Backend (Flask API on port 5000)
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m flask --app app run

# Terminal 2: Frontend (React UI on port 3000)
cd frontend
npm install
npm start
```

Then open http://localhost:3000.

## Configuration

- `linkedinBot/configs/config.yaml` stores UI defaults and bot preferences.
- Credentials are stored in browser localStorage (not sent to server except during bot actions).
- See [linkedinBot/README.md](linkedinBot/README.md) for bot-specific setup (LinkedIn account, API keys, etc).

New feature: post-search and email outreach

- Configure `settings.postSearch.keywords` with keywords to scan recent LinkedIn posts.
- Run the bot's `search_recent_posts` to collect posts and discovered emails to `linkedinBot/output/posts_emails.csv`.
- Use `send_emails_for_posts` (requires `GMAIL_USER` and `GMAIL_APP_PASSWORD` env vars) to send outreach messages to discovered addresses.

## Deployment

- **React frontend** → [Vercel](https://vercel.com) (free tier available)
- **Flask backend** → [Railway](https://railway.app), [Render](https://render.com), or [Heroku](https://heroku.com)

See [SETUP.md](SETUP.md) for deployment steps.

## Architecture

- `frontend/` — React UI, talks to Flask API
- `backend/` — Flask REST API, runs bot logic
- `linkedinBot/` — Bot core logic (unchanged from original)

## Notes

- Do not commit personal resumes, credentials, or generated output files into the repository.
- Upload your own PDF resumes via the UI or set environment variables.
- For production deployments, use proper secrets management (environment variables, vault services, etc).

