import argparse
import json
import os
import re
import sys
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
LOCAL_TIMEZONE = os.getenv('LOCAL_TIMEZONE', 'America/New_York')

# Tickets must look like a Jira issue key (e.g. EL-12345). Anything else
# (e.g. "Miscellaneous") is kept for personal time tracking and never logged.
JIRA_KEY_PATTERN = re.compile(r'^[A-Z][A-Z0-9]+-\d+$')


def parse_time_range(time_range):
    """Parse 'h:mm am - h:mm pm' into (start, end, duration_seconds)."""
    parts = time_range.split(' - ')
    if len(parts) != 2:
        raise ValueError(f"invalid time range '{time_range.strip()}'")
    start_time = datetime.strptime(parts[0].strip(), '%I:%M %p')
    end_time = datetime.strptime(parts[1].strip(), '%I:%M %p')
    duration = (end_time - start_time).total_seconds()
    if duration <= 0:
        raise ValueError(f"end time is not after start time in '{time_range.strip()}'")
    return start_time, end_time, duration


def adjust_datetime(date_str, time_obj):
    """Combine date and time, localize, and format as Jira UTC timestamp."""
    local_tz = pytz.timezone(LOCAL_TIMEZONE)
    date_dt = datetime.strptime(date_str.strip(), '%m/%d/%y')
    date_time = datetime.combine(date_dt, time_obj.time())
    local_time = local_tz.localize(date_time, is_dst=None)
    utc_time = local_time.astimezone(pytz.utc)
    return utc_time.strftime('%Y-%m-%dT%H:%M:%S.000+0000')


def validate_row(row):
    """Parse every time range in a row up front.

    Returns a list of (started_iso, duration_seconds) entries, or raises
    ValueError if anything in the row is invalid. Nothing is sent to Jira
    until the entire row validates.
    """
    entries = []
    for time_range in str(row['Times']).split('---'):
        start_time, _, duration = parse_time_range(time_range.strip())
        started = adjust_datetime(str(row['Date']), start_time)
        entries.append((started, int(duration)))
    return entries


def jira_auth():
    return HTTPBasicAuth(JIRA_USER, JIRA_API_TOKEN)


HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}


def add_worklog(issue_key, comment, started, time_spent_seconds):
    """Create a work log entry. Returns the new worklog id, or None on failure."""
    url = f"{JIRA_SERVER}/rest/api/3/issue/{issue_key}/worklog"
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
    response = requests.post(url, data=json.dumps(payload), headers=HEADERS, auth=jira_auth())
    if response.status_code == 201:
        worklog_id = response.json().get('id')
        print(f"  Logged {time_spent_seconds}s on {issue_key} starting {started} (worklog {worklog_id})")
        return worklog_id
    print(f"  Failed to create work log on {issue_key}: {response.status_code} {response.text}")
    return None


def delete_worklog(issue_key, worklog_id):
    """Delete a work log entry (used to roll back a partially logged row)."""
    url = f"{JIRA_SERVER}/rest/api/3/issue/{issue_key}/worklog/{worklog_id}"
    response = requests.delete(url, headers=HEADERS, auth=jira_auth())
    if response.status_code == 204:
        print(f"  Rolled back worklog {worklog_id} on {issue_key}")
        return True
    print(f"  WARNING: failed to roll back worklog {worklog_id} on {issue_key}: "
          f"{response.status_code} {response.text}")
    return False


def log_row(issue_key, description, entries):
    """Log all time ranges for a row, rolling back on partial failure.

    Returns True only if every entry was logged successfully.
    """
    created = []
    for started, duration in entries:
        worklog_id = add_worklog(issue_key, description, started, duration)
        if worklog_id is None:
            # Roll back anything already logged so the row stays unlogged.
            for wl_id in created:
                delete_worklog(issue_key, wl_id)
            return False
        created.append(worklog_id)
    return True


def is_blank(value):
    return pd.isna(value) or str(value).strip() == ''


def main():
    parser = argparse.ArgumentParser(description='Log work hours from a CSV file to Jira.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Validate the CSV and show what would be logged without calling Jira.')
    args = parser.parse_args()

    if args.dry_run:
        required = [('CSV_FILE_PATH', CSV_FILE_PATH)]
    else:
        required = [('JIRA_SERVER', JIRA_SERVER), ('JIRA_USER', JIRA_USER),
                    ('JIRA_API_TOKEN', JIRA_API_TOKEN), ('CSV_FILE_PATH', CSV_FILE_PATH)]
    missing = [name for name, value in required if not value]
    if missing:
        sys.exit(f"Missing required environment variables: {', '.join(missing)}")

    # Read everything as strings so the file is written back exactly as-is
    # (blank separator rows stay blank, TRUE stays TRUE).
    df = pd.read_csv(CSV_FILE_PATH, dtype=str)

    required_columns = ['Date', 'Times', 'Ticket', 'Logged', 'Description']
    missing_columns = [c for c in required_columns if c not in df.columns]
    if missing_columns:
        sys.exit(f"CSV file is missing required column(s): {', '.join(missing_columns)}")

    logged_count = skipped_count = error_count = 0

    for index, row in df.iterrows():
        # Skip blank separator rows and rows already logged.
        if is_blank(row['Date']) and is_blank(row['Times']) and is_blank(row['Ticket']):
            continue
        if not is_blank(row['Logged']) and str(row['Logged']).strip().upper() == 'TRUE':
            continue

        issue_key = str(row['Ticket']).strip()
        row_label = f"row {index + 2} ({row['Date']}, {issue_key})"

        # Skip non-Jira tickets (e.g. "Miscellaneous") kept for personal tracking.
        if not JIRA_KEY_PATTERN.match(issue_key):
            print(f"Skipping {row_label}: '{issue_key}' is not a Jira ticket key.")
            skipped_count += 1
            continue

        if is_blank(row['Date']) or is_blank(row['Times']):
            print(f"Skipping {row_label}: missing Date or Times.")
            error_count += 1
            continue

        # Validate the whole row before logging anything.
        try:
            entries = validate_row(row)
        except Exception as e:
            print(f"Skipping {row_label}: {e}. Nothing was logged for this row.")
            error_count += 1
            continue

        description = '' if is_blank(row['Description']) else str(row['Description'])

        if args.dry_run:
            total = sum(duration for _, duration in entries)
            print(f"[dry-run] Would log {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} "
                  f"({int(total) // 3600}h {int(total) % 3600 // 60}m) on {row_label}")
            logged_count += 1
            continue

        print(f"Logging {row_label}...")
        if log_row(issue_key, description, entries):
            df.at[index, 'Logged'] = 'TRUE'
            logged_count += 1
        else:
            print(f"  Row not marked as logged; fix the issue and rerun.")
            error_count += 1

    if not args.dry_run:
        try:
            df.to_csv(CSV_FILE_PATH, index=False)
        except Exception as e:
            sys.exit(f"Failed to save CSV file: {e}")

    action = 'validated' if args.dry_run else 'logged'
    print(f"\nDone. {logged_count} row(s) {action}, {skipped_count} skipped (non-Jira), "
          f"{error_count} error(s).")


if __name__ == '__main__':
    main()
