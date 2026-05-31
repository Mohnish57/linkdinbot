import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import os
import yaml


def upload_csv_to_gsheet(csv_file, sheet_name, gsheet_url):
    # Authenticate with Google Sheets
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(os.environ['GOOGLE_APPLICATION_CREDENTIALS'], scopes=scope)
    client = gspread.authorize(creds)

    # Open the Google Sheet
    sheet = client.open_by_url(gsheet_url)
    try:
        worksheet = sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=sheet_name, rows="1000", cols="20")

    df = pd.read_csv(csv_file, encoding="utf-8-sig").fillna('')  # Replace NaN with empty strings

    # Convert DataFrame to a list of lists
    data = [df.columns.tolist()] + df.astype(str).values.tolist()  # Ensure all values are strings

    # Resize worksheet to fit data
    worksheet.resize(rows=len(data), cols=len(df.columns))

    # Clear existing data & update sheet
    worksheet.clear()
    worksheet.update(data)

    print("✅ File uploaded successfully!")

def main():
    csv_file = "linkedinBot\output\jobs.csv"
    sheet_name = f"Jobs_{pd.Timestamp.now().strftime('%Y-%m-%d')}"
    with open('linkedinBot\configs\config.yaml') as f:
        config = yaml.safe_load(f)
    gsheet_url = f"https://docs.google.com/spreadsheets/d/{config['gsheet_id']}"

    upload_csv_to_gsheet(csv_file, sheet_name, gsheet_url)

if __name__ == "__main__":
    main()