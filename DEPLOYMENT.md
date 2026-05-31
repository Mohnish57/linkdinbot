# Deployment Guide

This document explains how to deploy the LinkedIn Bot (React UI + Flask API) to the cloud.

## Overview

The app consists of two parts:
- **Frontend**: React UI (static files) → Deploy to Vercel, Netlify, or GitHub Pages
- **Backend**: Flask API (Python server) → Deploy to Railway, Render, Heroku, etc.

## Frontend deployment (React → Vercel)

### Prerequisites
- GitHub account with repo pushed
- Vercel account (free tier available)

### Steps

1. Go to [vercel.com](https://vercel.com/dashboard)
2. Click **Add New → Project**
3. Import your GitHub repository
4. Set **Root Directory** to `frontend`
5. Add environment variable:
   - Key: `REACT_APP_API_URL`
   - Value: `https://your-backend-url.com` (e.g., Railway/Render API URL)
6. Click **Deploy**

Vercel will auto-deploy when you push to `main` branch.

---

## Backend deployment (Flask → Railway)

### Prerequisites
- GitHub account
- Railway account (free tier available at [railway.app](https://railway.app))

### Steps

1. Go to [railway.app/dashboard](https://railway.app/dashboard)
2. Click **New Project → Deploy from GitHub repo**
3. Select your repo
4. Railway will auto-detect a Python project
5. Add environment variables (use Railway's GUI):
   - `LINKEDIN_EMAIL`
   - `LINKEDIN_PASSWORD`
   - `GEMINI_API_KEY`
   - `GMAIL_USER`
   - `GMAIL_APP_PASSWORD`
   - `FLASK_ENV=production`
6. Configure build command: `pip install -r backend/requirements.txt`
7. Configure start command: `cd backend && gunicorn app:app`
8. Deploy

Railway will give you a public URL (e.g., `https://linkedinbot-prod.railway.app`).

5. Update your frontend's `REACT_APP_API_URL` environment variable in Vercel to this URL.

---

## Backend deployment alternatives

### Option A: Render.com

1. Go to [render.com](https://render.com)
2. **New → Web Service**
3. Connect GitHub repo
4. Use these settings:
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `cd backend && gunicorn app:app`
   - Add environment variables in the UI
5. Deploy

### Option B: Heroku (legacy, not free anymore)

If you prefer Heroku:
1. Install Heroku CLI: `brew install heroku` (macOS)
2. `heroku login`
3. `heroku create your-app-name`
4. `git push heroku main` (pushes entire repo)
5. Set environment variables: `heroku config:set KEY=value`

---

## Testing before deployment

### Local testing (before pushing)

```bash
# Terminal 1: Backend
cd backend
export FLASK_ENV=production
gunicorn app:app --bind 0.0.0.0:5000

# Terminal 2: Frontend
cd frontend
REACT_APP_API_URL=http://localhost:5000 npm start
```

---

## Troubleshooting

### "404 NOT_FOUND" on Vercel
- You're trying to deploy the entire monorepo to Vercel, which expects a single static site.
- **Fix**: Set Vercel's **Root Directory** to `frontend`.

### Backend returns 502 Bad Gateway
- Check that all environment variables are set correctly.
- Check backend logs on Railway/Render dashboard.
- Ensure `gunicorn` is installed: `pip install gunicorn`.

### Frontend can't reach backend API
- Check that `REACT_APP_API_URL` is set correctly in your deployment.
- Ensure backend is publicly accessible (not in private network).
- Check browser console for CORS errors.

### Bot hangs or times out
- Selenium + Chrome headless can take time. Increase timeout or use `headless=True`.
- On cloud platforms, memory/CPU limits might be too low. Upgrade if needed.

---

## Cost estimates (as of 2024)

- **Vercel** (React): Free tier included, $20/mo for Pro
- **Railway** (Flask): Free $5 credit/mo, then pay-per-use (~$0.10/hour for app)
- **Render** (Flask): Free tier available, but sleeps after 15 min inactivity
- **GitHub Actions** (CI/CD): Free for public repos

---

## Next steps

1. Test locally (`npm start` + Flask dev server)
2. Push to GitHub
3. Deploy frontend to Vercel
4. Deploy backend to Railway
5. Update frontend's API URL
6. Test live!

For questions, see the main [README.md](README.md) or [SETUP.md](SETUP.md).
