# LinkedIn Bot

This repository contains a configurable LinkedIn automation tool that combines Selenium browser automation, AI job matching, and email outreach.

## Project structure

- `app.py`: Streamlit UI for configuration and running the bot
- `run_bot.py`: CLI runner for non-UI execution
- `linkedinBot/bot.py`: core LinkedIn automation logic
- `linkedinBot/configs/config.yaml`: persisted settings and templates
- `linkedinBot/output/`: generated CSV outputs
- `linkedinBot/uploads/`: uploaded resume PDFs from the Streamlit UI
- `linkedinBot/utils/`: helper utilities for AI, mail, shortlinks, and Google Sheets

## Setup

1. Activate your Python environment
2. Install dependencies:
   ```bash
   pip install -r linkedinBot/requirements.txt
   ```
3. Set environment variables for LinkedIn and Gemini credentials
4. Customize `linkedinBot/configs/config.yaml`

## Running

- UI mode:
  ```bash
  streamlit run app.py
  ```
- CLI mode:
  ```bash
  python run_bot.py
  ```
