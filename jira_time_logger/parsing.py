"""Parsing and validation helpers for work log CSV rows."""

import re
from datetime import datetime, timedelta

import pandas as pd
import pytz

# Tickets must look like a Jira issue key (e.g. EL-12345). Anything else
# (e.g. "Miscellaneous") is kept for personal time tracking and never logged.
JIRA_KEY_PATTERN = re.compile(r'^[A-Z][A-Z0-9]+-\d+$')


def parse_time_range(time_range):
    """Parse 'h:mm am - h:mm pm' into (start, end, duration_seconds).

    Ranges that end before the start time are treated as crossing midnight
    (e.g. '11:00 pm - 1:00 am' is 2 hours); equal start and end times are
    rejected as zero-length.
    """
    parts = time_range.split(' - ')
    if len(parts) != 2:
        raise ValueError(f"invalid time range '{time_range.strip()}'")
    start_time = datetime.strptime(parts[0].strip(), '%I:%M %p')
    end_time = datetime.strptime(parts[1].strip(), '%I:%M %p')
    if end_time == start_time:
        raise ValueError(f"zero-length time range '{time_range.strip()}'")
    if end_time < start_time:
        end_time += timedelta(days=1)  # overnight range
    duration = (end_time - start_time).total_seconds()
    return start_time, end_time, duration


def adjust_datetime(date_str, time_obj, timezone_name):
    """Combine date and time, localize, and format as Jira UTC timestamp."""
    local_tz = pytz.timezone(timezone_name)
    date_dt = datetime.strptime(date_str.strip(), '%m/%d/%y')
    date_time = datetime.combine(date_dt, time_obj.time())
    local_time = local_tz.localize(date_time, is_dst=None)
    utc_time = local_time.astimezone(pytz.utc)
    return utc_time.strftime('%Y-%m-%dT%H:%M:%S.000+0000')


def validate_row(row, timezone_name):
    """Parse every time range in a row up front.

    Returns a list of (started_iso, duration_seconds) entries, or raises
    ValueError if anything in the row is invalid. Nothing is sent to Jira
    until the entire row validates.
    """
    entries = []
    for time_range in str(row['Times']).split('---'):
        start_time, _, duration = parse_time_range(time_range.strip())
        started = adjust_datetime(str(row['Date']), start_time, timezone_name)
        entries.append((started, int(duration)))
    return entries


def row_total_seconds(row):
    """Total seconds across all time ranges in a row (raises on bad data)."""
    return sum(parse_time_range(tr.strip())[2] for tr in str(row['Times']).split('---'))


def is_blank(value):
    return pd.isna(value) or str(value).strip() == ''


def format_duration(seconds):
    return f"{int(seconds) // 3600}h {int(seconds) % 3600 // 60}m"


def truncate(text, width=60):
    return text if len(text) <= width else text[:width - 3] + '...'
