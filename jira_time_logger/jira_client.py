"""Thin client for the Jira work log REST API."""

import json

import requests
from requests.auth import HTTPBasicAuth

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}


class JiraClient:
    def __init__(self, server, user, api_token, timeout=30):
        self.server = server
        self.auth = HTTPBasicAuth(user, api_token)
        self.timeout = timeout

    def add_worklog(self, issue_key, comment, started, time_spent_seconds):
        """Create a work log entry. Returns the new worklog id, or None on failure."""
        url = f"{self.server}/rest/api/3/issue/{issue_key}/worklog"
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
        try:
            response = requests.post(url, data=json.dumps(payload), headers=HEADERS,
                                     auth=self.auth, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            print(f"          -> request failed: {e}")
            return None
        if response.status_code == 201:
            return response.json().get('id')
        print(f"          -> Jira rejected worklog: {response.status_code} {response.text}")
        return None

    def delete_worklog(self, issue_key, worklog_id):
        """Delete a work log entry (used to roll back a partially logged row)."""
        url = f"{self.server}/rest/api/3/issue/{issue_key}/worklog/{worklog_id}"
        try:
            response = requests.delete(url, headers=HEADERS, auth=self.auth, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            print(f"          -> WARNING: failed to roll back worklog {worklog_id} on {issue_key}: {e}")
            return False
        if response.status_code == 204:
            print(f"          -> rolled back worklog {worklog_id} on {issue_key}")
            return True
        print(f"          -> WARNING: failed to roll back worklog {worklog_id} on {issue_key}: "
              f"{response.status_code} {response.text}")
        return False

    def log_row(self, issue_key, description, entries):
        """Log all time ranges for a row, rolling back on partial failure.

        Returns True only if every entry was logged successfully.
        """
        created = []
        for started, duration in entries:
            worklog_id = self.add_worklog(issue_key, description, started, duration)
            if worklog_id is None:
                # Roll back anything already logged so the row stays unlogged.
                for wl_id in created:
                    self.delete_worklog(issue_key, wl_id)
                return False
            created.append(worklog_id)
        return True
