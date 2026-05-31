# LinkedIn Referral Bot

A configurable LinkedIn outreach automation project that searches jobs, evaluates matches, connects with recruiters, and optionally sends follow-up email outreach.

## Features

- AI-assisted job matching and recruiter outreach
- Configurable job searches, recruiter filters, invite templates, and email templates
- Streamlit UI for interactive setup and run control
- Optional CLI runner for headless operation

## Quickstart

```bash
cd path/to/project
source .venv/bin/activate
pip install -r linkedinBot/requirements.txt
```

### Run the UI

```bash
streamlit run app.py
```

### Run the bot from the command line

```bash
python run_bot.py
```

## Configuration

- `linkedinBot/configs/config.yaml` stores UI defaults and bot preferences.
- `.env.example` is a template for environment variables like `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD`, `GEMINI_API_KEY`, and resume paths.
- Candidate information, invite templates, and email templates are all configurable.

## Notes

- Do not commit personal resumes, credentials, or generated output files into the repository.
- Upload your own PDF resumes via the Streamlit UI or set `RESUME_PATH_FULLSTACK` / `RESUME_PATH_FRONTEND` in your environment.
