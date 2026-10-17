import argparse
import os
import sys
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

from jira_time_logger.jira_client import JiraClient
from jira_time_logger.parsing import (JIRA_KEY_PATTERN, format_duration, is_blank,
                                      row_total_seconds, truncate, validate_row)

# Load environment variables from .env file
load_dotenv()

# Configuration
JIRA_SERVER = os.getenv('JIRA_SERVER')
JIRA_USER = os.getenv('JIRA_USER')
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')
CSV_FILE_PATH = os.getenv('CSV_FILE_PATH')
LOCAL_TIMEZONE = os.getenv('LOCAL_TIMEZONE', 'America/New_York')

# Seconds to wait for Jira API responses before giving up.
REQUEST_TIMEOUT = 30


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

    csv_path = CSV_FILE_PATH
    if csv_path is None:  # unreachable; narrows the type for static checkers
        sys.exit("Missing required environment variables: CSV_FILE_PATH")

    # Read everything as strings so the file is written back exactly as-is
    # (blank separator rows stay blank, TRUE stays TRUE).
    df = pd.read_csv(csv_path, dtype=str)

    required_columns = ['Date', 'Times', 'Ticket', 'Logged', 'Description']
    missing_columns = [c for c in required_columns if c not in df.columns]
    if missing_columns:
        sys.exit(f"CSV file is missing required column(s): {', '.join(missing_columns)}")

    client = None if args.dry_run else JiraClient(JIRA_SERVER, JIRA_USER, JIRA_API_TOKEN,
                                                  timeout=REQUEST_TIMEOUT)

    logged_count = skipped_count = error_count = 0
    day_totals = {}  # date string -> [jira_seconds, all_seconds] for rows processed this run
    active_days = set()  # dates with loggable (Jira) rows this run; limits the totals report
    current_date = None

    def add_day_total(day, seconds, jira):
        totals = day_totals.setdefault(day, [0, 0])
        if jira:
            totals[0] += seconds
        totals[1] += seconds

    def ensure_date_header(day):
        nonlocal current_date
        if day != current_date:
            current_date = day
            print(f"\n{day}")

    def print_row(day, status, ticket, text):
        ensure_date_header(day)
        print(f"  [{status:<5}] {ticket:<14} {text}")

    if args.dry_run:
        print("Dry run - nothing will be sent to Jira.")

    for position, (index, row) in enumerate(df.iterrows()):
        csv_row_number = position + 2  # 1-based, accounting for the header row
        # Skip blank separator rows and rows already logged.
        if is_blank(row['Date']) and is_blank(row['Times']) and is_blank(row['Ticket']):
            continue
        if not is_blank(row['Logged']) and str(row['Logged']).strip().upper() == 'TRUE':
            continue

        issue_key = str(row['Ticket']).strip()
        date_str = '(no date)' if is_blank(row['Date']) else str(row['Date']).strip()

        # Non-Jira tickets (e.g. "Miscellaneous") are personal tracking entries:
        # count them toward day totals but keep them out of the per-row output.
        if not JIRA_KEY_PATTERN.match(issue_key):
            skipped_count += 1
            try:
                add_day_total(date_str, row_total_seconds(row), jira=False)
            except ValueError:
                pass  # unparseable personal entries are ignored
            continue

        active_days.add(date_str)

        if is_blank(row['Date']) or is_blank(row['Times']):
            print_row(date_str, 'ERROR', issue_key, f"row {csv_row_number}: missing Date or Times")
            error_count += 1
            continue

        # Validate the whole row before logging anything.
        try:
            entries = validate_row(row, LOCAL_TIMEZONE)
        except Exception as e:
            print_row(date_str, 'ERROR', issue_key,
                      f"row {csv_row_number}: {e} - nothing logged for this row")
            error_count += 1
            continue

        description = '' if is_blank(row['Description']) else str(row['Description'])
        total = sum(duration for _, duration in entries)
        ranges = f"{len(entries)} range{'' if len(entries) == 1 else 's'}"
        detail = f"{format_duration(total):>7}  {ranges:<9} {truncate(description)}"

        if args.dry_run:
            add_day_total(date_str, total, jira=True)
            print_row(date_str, 'DRY', issue_key, detail)
            logged_count += 1
            continue

        ensure_date_header(date_str)  # so any API error detail prints under the right day
        assert client is not None  # dry-run rows never reach this point
        if client.log_row(issue_key, description, entries):
            df.at[index, 'Logged'] = 'TRUE'
            add_day_total(date_str, total, jira=True)
            print_row(date_str, 'OK', issue_key, detail)
            logged_count += 1
        else:
            add_day_total(date_str, total, jira=False)  # time exists in the CSV but was not logged
            print_row(date_str, 'FAIL', issue_key,
                      f"row {csv_row_number}: Jira call failed - row left unlogged, fix and rerun")
            error_count += 1

    if not args.dry_run:
        try:
            df.to_csv(csv_path, index=False)
        except Exception as e:
            sys.exit(f"Failed to save CSV file: {e}")

    reported_days = {d: s for d, s in day_totals.items() if d in active_days}
    if reported_days:
        def date_key(d):
            try:
                return datetime.strptime(d, '%m/%d/%y')
            except ValueError:
                return datetime.max
        print(f"\n{'-' * 40}")
        print("Day totals:")
        print(f"  {'Date':<10} {'Jira':>8} {'All':>8}")
        for date_str in sorted(reported_days, key=date_key):
            jira_s, all_s = reported_days[date_str]
            print(f"  {date_str:<10} {format_duration(jira_s):>8} {format_duration(all_s):>8}")

    action = 'validated' if args.dry_run else 'logged'
    print(f"\nSummary: {logged_count} row(s) {action}, {skipped_count} non-Jira row(s) skipped, "
          f"{error_count} error(s).")


if __name__ == '__main__':
    main()
