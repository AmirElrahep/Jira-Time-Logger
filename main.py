import json
import os
from datetime import datetime
import pandas as pd
import pytz
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

# Load environment variables from .env file
load_dotenv()

# Configuration
JIRA_SERVER = os.getenv('JIRA_SERVER')
JIRA_USER = os.getenv('JIRA_USER')
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')
CSV_FILE_PATH = os.getenv('CSV_FILE_PATH')

df = pd.read_csv(CSV_FILE_PATH)

# Ensure 'Logged' column is of boolean type and replace NaN values with False
df['Logged'] = df['Logged'].astype('boolean')
df['Logged'] = df['Logged'].fillna(False)


# Function to parse and calculate duration
def parse_time_range(time_range):
    start_time_str, end_time_str = time_range.split(' - ')
    start_time = datetime.strptime(start_time_str.strip(), '%I:%M %p')
    end_time = datetime.strptime(end_time_str.strip(), '%I:%M %p')
    return start_time, end_time, (end_time - start_time).total_seconds()


# Function to adjust date and time for Jira
def adjust_datetime(date_str, time_obj):
    # Define local timezone
    local_tz = pytz.timezone('America/New_York')  # Update this to your local timezone

    date_dt = datetime.strptime(date_str, '%m/%d/%y')
    date_time = datetime.combine(date_dt, time_obj.time())

    # Localize to local timezone
    local_time = local_tz.localize(date_time, is_dst=None)

    # Convert to UTC
    utc_time = local_time.astimezone(pytz.utc)

    return utc_time.strftime('%Y-%m-%dT%H:%M:%S.000+0000')


# Function to create a work log entry
def add_worklog(issue_key, comment, started, time_spent_seconds):
    url = f"{JIRA_SERVER}/rest/api/3/issue/{issue_key}/worklog"
    auth = HTTPBasicAuth(JIRA_USER, JIRA_API_TOKEN)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "comment": {
            "content": [
                {
                    "content": [
                        {
                            "text": comment,
                            "type": "text"
                        }
                    ],
                    "type": "paragraph"
                }
            ],
            "type": "doc",
            "version": 1
        },
        "started": started,
        "timeSpentSeconds": time_spent_seconds
    }
    response = requests.post(url, data=json.dumps(payload), headers=headers, auth=auth)
    if response.status_code == 201:
        print(f"Work log added successfully: {response.json()}")
        return True
    else:
        print(f"Failed to create work log entry: {response.text}")
        return False


# Iterate through the rows and add work logs
for index, row in df.iterrows():
    if not row['Logged']:
        date_str = row['Date']
        issue_key = row['Ticket']
        time_ranges = row['Times'].split('---')
        description = row['Description']

        for time_range in time_ranges:
            try:
                start_time, end_time, duration = parse_time_range(time_range.strip())
                start_time_iso = adjust_datetime(date_str, start_time)
                if add_worklog(issue_key, description, start_time_iso, int(duration)):
                    df.at[index, 'Logged'] = True
            except Exception as e:
                print(f"Failed to log work for issue {issue_key}: {e}")

# Save the updated CSV file
try:
    df.to_csv(CSV_FILE_PATH, index=False)
    print("Work logs processing completed and CSV file saved.")
except Exception as e:
    print(f"Failed to save CSV file: {e}")
