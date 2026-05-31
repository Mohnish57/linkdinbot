# LinkedIn Bot — React + Flask Setup

## Project structure

```
linkdinbot/
├── backend/              # Flask API
│   ├── app.py            # Main API server
│   ├── requirements.txt   # Backend dependencies
│   └── venv/             # Virtual environment (create locally)
├── frontend/             # React UI
│   ├── public/
│   ├── src/
│   ├── package.json
│   ├── .env              # API URL config
│   └── node_modules/     # Dependencies (npm install)
└── linkedinBot/          # Bot logic (unchanged)
    ├── bot.py
    ├── utils/
    ├── configs/config.yaml
    └── output/           # Results (jobs.csv, connections.csv, posts_emails.csv)
```

## Quick start

### Backend (Flask API)

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run API server (port 5000)
python -m flask --app app run
```

### Frontend (React UI)

In a new terminal:

```bash
cd frontend

# Install dependencies
npm install

# Start React dev server (port 3000)
npm start
```

Then open http://localhost:3000 in your browser.

## Environment configuration

**Frontend (frontend/.env):**
```
REACT_APP_API_URL=http://localhost:5000
```

For production, update this to your deployed API URL.

**Backend:**
Set environment variables for LinkedIn credentials, Gemini API key, etc. See the bot's README for details.

## How to deploy

### Frontend (React → Vercel)
1. Push repo to GitHub
2. Go to [vercel.com](https://vercel.com)
3. Import repository → select `frontend` as root directory
4. Set `REACT_APP_API_URL` environment variable to your backend API URL
5. Deploy

### Backend (Flask → Railway / Render / Heroku)
1. Choose a platform that supports long-running Python apps
2. Create `Procfile`:
   ```
   web: gunicorn app:app
   ```
3. Deploy with your API URL
4. Update frontend's `REACT_APP_API_URL` to point to the deployed backend

## Development

- **Add new API endpoint**: Edit `backend/app.py`
- **Add new React component**: Create file in `frontend/src/components/`
- **Update config**: Edit `linkedinBot/configs/config.yaml`

## Credentials handling

Credentials are stored in browser's localStorage when you fill the sidebar in the React UI. They are NOT sent to the server except when you click a bot action button (run, search, etc).

For production, consider:
- Using a proper secrets management system
- Environment variables on the backend
- Token-based auth if shared backend

See the original `linkedinBot/README.md` for bot-specific setup (LinkedIn account, Gemini API key, Gmail app password, etc).
