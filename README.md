# Jira Time Logger

This project automates the process of logging work hours into Jira by reading data from a CSV file and making API
requests to Jira's REST API.

## Features

- Reads work log data from a CSV file.
- Parses and calculates work durations.
- Converts local time to UTC for Jira compatibility.
- Adds work logs to Jira issues using the REST API.
- Updates the CSV file to mark successfully logged entries.
- All-or-nothing rows: every time range in a row is validated before anything is sent to Jira, and if a later
  range fails mid-row, the already-created work logs for that row are automatically deleted (rolled back) so the
  row is never left partially logged.
- Skips blank separator rows, so you can visually group days in your CSV.
- Skips rows whose `Ticket` is not a Jira issue key (e.g. `Miscellaneous`), letting you keep personal
  time-tracking entries in the same file without logging them.
- `--dry-run` mode to validate the CSV and preview what would be logged without calling Jira.
- Supports overnight time ranges (e.g. `11:00 pm - 1:00 am` counts as 2 hours).
- Prints per-day time totals (including non-Jira entries) so you can spot days that don't add up.
- API requests time out after 30 seconds instead of hanging indefinitely.
- Preserves your CSV formatting when saving (blank rows stay blank, `TRUE` stays `TRUE`).
- Prints a summary of logged, skipped, and errored rows.

## Project Structure

- `main.py` - CLI entry point: configuration, CSV processing loop, and console output.
- `jira_time_logger/parsing.py` - time range parsing, validation, and formatting helpers.
- `jira_time_logger/jira_client.py` - Jira work log REST API client with rollback support.
- `tests/` - unit tests for the parsing and validation logic.

## Requirements

- Python 3.6+
- `pandas` library
- `requests` library
- `pytz` library
- `python-dotenv` library
- Jira account with API access

## Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/AmirElrahep/Jira-Time-Logger.git
   ```

2. **Create and activate a virtual environment (optional but recommended):**

    ```bash
    python -m venv .venv
    ```

    - **On Windows:**
      ```bash
      .\.venv\Scripts\activate
      ```

    - **On macOS/Linux:**
      ```bash
      source .venv/bin/activate
      ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**

   Create a `.env` file in the root directory of the project and add your server URL, Jira credentials, and path to your
   CSV file:

   ```env
   JIRA_SERVER=https://your-domain.atlassian.net
   JIRA_USER=your-email@example.com
   JIRA_API_TOKEN=your-api-token
   CSV_FILE_PATH=C:\path\to\your\JiraWorkLogs.csv
   LOCAL_TIMEZONE=America/New_York
   ```

   `LOCAL_TIMEZONE` is optional and defaults to `America/New_York`.

5. **Prepare the CSV file:**

   Make sure your CSV file (`JiraWorkLogs.csv`) is formatted as follows:

    ```csv
    Date,Times,Ticket,Logged,Description
    7/24/24,8:40 pm - 10:00 pm --- 10:30 pm - 11:00 pm,EL-27466,,Working on program to automate time logging.
    7/24/24,11:00 pm - 11:15 pm,Miscellaneous,,Personal tracking entry that is never sent to Jira.
    ,,,,
    7/25/24,9:00 am - 9:10 am,EL-27466,,Stand-Up
    ```

    - `Date`: Date of the work log in `mm/dd/yy` format.
    - `Times`: Time ranges in `hh:mm am/pm` format, separated by `---` if multiple.
    - `Ticket`: Jira ticket key. Any value that doesn't look like a Jira key (e.g. `Miscellaneous`) is skipped,
      so you can keep personal time-tracking entries in the same file.
    - `Logged`: Leave empty initially; will be updated to `TRUE` after all time ranges in the row are logged.
    - `Description`: Description of the work done.
    - Fully blank rows (`,,,,`) are ignored, so you can use them to visually separate days.

## Running the Script

Execute the script to read the CSV file, log work hours to Jira, and update the CSV file:

```bash
python main.py
```

To validate your CSV and preview what would be logged without sending anything to Jira:

```bash
python main.py --dry-run
```

## Running the Tests

Install the development dependencies and run pytest:

```bash
pip install -r requirements-dev.txt
pytest
```

## Deactivate the Virtual Environment (Optional):

When you are done, you can deactivate the virtual environment by running:

```bash
deactivate
```