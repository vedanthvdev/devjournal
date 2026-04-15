"""Jira collector — active tickets and daily activity via the Atlassian REST API."""

from __future__ import annotations

import logging
import re
from datetime import date

import requests

from devjournal.collector import Collector, CollectorResult

log = logging.getLogger("devjournal")

_PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")


class JiraCollector(Collector):
    name = "jira"
    config_key = "jira"

    @staticmethod
    def _safe_project_list(config: dict) -> str:
        raw = config.get("projects", [])
        valid = [p for p in raw if _PROJECT_KEY_RE.match(p)]
        if len(valid) != len(raw):
            skipped = set(raw) - set(valid)
            log.warning("Skipped invalid Jira project keys: %s", skipped)
        return ",".join(valid)

    def collect(self, target_date: date, config: dict) -> CollectorResult:
        """Tickets the user touched or commented on today."""
        projects = self._safe_project_list(config)
        if not projects:
            log.warning("No valid Jira project keys configured — skipping collect")
            return CollectorResult(
                section_id="jira_activity",
                heading="### Jira Activity",
                empty_message="No Jira activity today.",
            )
        date_str = target_date.isoformat()
        jql = (
            f"project in ({projects}) AND "
            f"(assignee = currentUser() OR reporter = currentUser() OR "
            f'comment ~ currentUser()) AND updated >= "{date_str}" '
            f"ORDER BY updated DESC"
        )
        issues = self._search(config, jql, ["summary", "status", "updated"])
        domain = config.get("domain", "")
        items = [
            {
                "key": i["key"],
                "summary": i["fields"].get("summary", ""),
                "status": i["fields"].get("status", {}).get("name", ""),
                "link": f"https://{domain}/browse/{i['key']}",
            }
            for i in issues
        ]
        return CollectorResult(
            section_id="jira_activity",
            heading="### Jira Activity",
            items=items,
            empty_message="No Jira activity today.",
        )

    def collect_agenda(self, target_date: date, config: dict) -> CollectorResult:
        """Active tickets assigned to the user (morning agenda)."""
        projects = self._safe_project_list(config)
        if not projects:
            log.warning("No valid Jira project keys configured — skipping agenda")
            return CollectorResult(
                section_id="jira_active",
                heading="### Jira Tickets (Active)",
                empty_message="No active tickets found.",
            )
        jql = (
            f"project in ({projects}) AND assignee = currentUser() "
            f"AND statusCategory != Done ORDER BY updated DESC"
        )
        issues = self._search(config, jql, ["summary", "status", "priority", "issuetype"])
        domain = config.get("domain", "")
        items = [
            {
                "key": i["key"],
                "summary": i["fields"].get("summary", ""),
                "status": i["fields"].get("status", {}).get("name", ""),
                "priority": i["fields"].get("priority", {}).get("name", ""),
                "type": i["fields"].get("issuetype", {}).get("name", ""),
                "link": f"https://{domain}/browse/{i['key']}",
            }
            for i in issues
        ]
        return CollectorResult(
            section_id="jira_active",
            heading="### Jira Tickets (Active)",
            items=items,
            empty_message="No active tickets found.",
        )

    @staticmethod
    def _search(config: dict, jql: str, fields: list[str], max_results: int = 50) -> list[dict]:
        domain = config.get("domain", "")
        email = config.get("email", "")
        token = config.get("api_token", "")
        if not all([domain, email, token]):
            log.warning("Jira not fully configured — skipping")
            return []
        url = f"https://{domain}/rest/api/3/search/jql"
        try:
            r = requests.post(
                url,
                auth=(email, token),
                json={"jql": jql, "maxResults": max_results, "fields": fields},
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("issues", [])
        except Exception as e:
            log.warning("Jira search failed: %s", e)
            return []
