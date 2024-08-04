# Jira Time Logger

This project automates the process of logging work hours into Jira by reading data from a CSV file and making API
requests to Jira's REST API.

## Features

- Reads work log data from a CSV file.
- Parses and calculates work durations.
- Converts local time to UTC for Jira compatibility.
- Adds work logs to Jira issues using the REST API.
- Updates the CSV file to mark successfully logged entries.

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
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. **Install dependencies:**
   ```bash
    pip install -r requirements.txt
    ```

4. **Set up environment variables:**

   Create a `.env` file in the root directory of the project and add your Jira credentials and server URL:

   ```env
   JIRA_SERVER=https://your-domain.atlassian.net
   JIRA_USER=your-email@example.com
   JIRA_API_TOKEN=your-api-token
   CSV_FILE_PATH=C:\path\to\your\JiraWorkLogs.csv
   ```

5. **Prepare the CSV file:**

   Make sure your CSV file (`JiraWorkLogs.csv`) is formatted as follows:

    ```csv
    Date,Times,Ticket,Logged,Description
    7/24/24,8:40 pm - 10:00 pm --- 10:30 pm - 11:00 pm,EL-27466,False,Working on program to automate time logging.
    ```

    - `Date`: Date of the work log in `mm/dd/yy` format.
    - `Times`: Time ranges in `hh:mm am/pm` format, separated by `---` if multiple.
    - `Ticket`: Jira ticket key.
    - `Logged`: Leave empty or set to `False` initially; will be updated to `True` after logging.
    - `Description`: Description of the work done.

## Running the Script

Execute the script to read the CSV file, log work hours to Jira, and update the CSV file:

```bash
python main.py
