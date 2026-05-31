# LinkedIn Bot

This project is a LinkedIn automation bot designed to streamline job applications and networking. It leverages Selenium for browser automation and integrates with Google Sheets and AI tools to evaluate job matches and manage data.

## Features

- **Automated Job Applications**: Searches and applies for jobs based on user-defined preferences.
- **Job Match Evaluation**: Uses AI to evaluate job descriptions against your resume for suitability.
- **Networking Automation**: Connects with relevant professionals from companies on LinkedIn.
- **Data Management**: Saves job details and connections to a CSV file and uploads them to Google Sheets.
- **Customizable Settings**: Configure job preferences, blacklisted titles, and more through a YAML configuration file.

## Project Structure

- **configs/**: Contains configuration files.
- **output/**: Stores generated CSV files with job details.
- **src/**: Source code for the bot.

## Installation

1. Clone the repository:
  ```bash
  git clone https://github.com/yourusername/linkedinBot.git
  cd linkedinBot
  ```

2. Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

3. Set up environment variables:
  - `GOOGLE_APPLICATION_CREDENTIALS`: Path to your Google service account JSON file.
  - `GEMINI_API_KEY`: API key for Gemini AI.
  - `LINKEDIN_EMAIL`: Your LinkedIn email.
  - `LINKEDIN_PASSWORD`: Your LinkedIn password.

4. Update the configuration file:
  Modify `configs/config.yaml` to set your job preferences and settings.

## Usage

### Running the Bot

Start the bot:
```bash
python bot.py
```

The bot will:
- Log in to LinkedIn.
- Search for jobs based on your preferences.
- Evaluate job matches using AI.
- Save job details to `output/jobs.csv`.

Optionally, populate connections:

### Uploading Data to Google Sheets

Run the following command to upload job details to Google Sheets:
```bash
python utils/gsheet.py
```

## Configuration

The bot's behavior can be customized through the `configs/config.yaml` file. Key settings include:
- **Job Types**: Full-time, part-time, contract, etc.
- **Date Posted**: Filter jobs by posting date.
- **Positions**: List of job titles to search for.
- **Blacklisted Titles**: Exclude jobs with specific titles.
- **Employee Count**: Filter companies by size.

## Dependencies

The project requires the following Python libraries:
- Selenium
- PyAutoGUI
- Pandas
- Google Sheets API
- Gemini AI SDK
- And more (see `requirements.txt` for the full list)

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## Disclaimer

This bot is intended for educational purposes only. Use it responsibly and ensure compliance with LinkedIn's terms of service.
```
