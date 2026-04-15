"""Confluence collector — pages created or edited today."""

from __future__ import annotations

import logging
from datetime import date

import requests

from devjournal.collector import Collector, CollectorResult

log = logging.getLogger("devjournal")


class ConfluenceCollector(Collector):
    name = "confluence"
    config_key = "confluence"

    def collect(self, target_date: date, config: dict) -> CollectorResult:
        pages = self._fetch(target_date, config)
        return CollectorResult(
            section_id="confluence",
            heading="### Confluence",
            items=pages,
            empty_message="No Confluence activity today.",
        )

    def _fetch(self, target_date: date, config: dict) -> list[dict]:
        domain = config.get("domain", "")
        email = config.get("email", "")
        token = config.get("api_token", "")

        if not all([domain, email, token]):
            log.warning("Confluence not fully configured — skipping")
            return []

        date_str = target_date.isoformat()
        cql = f'contributor = currentUser() AND lastModified >= "{date_str}"'
        url = f"https://{domain}/wiki/rest/api/content/search"

        try:
            r = requests.get(
                url,
                auth=(email, token),
                params={"cql": cql, "limit": 25},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning("Confluence request failed: %s", e)
            return []

        pages: list[dict] = []
        for result in data.get("results", []):
            title = result.get("title", "")
            links = result.get("_links", {})
            link = ""
            if "webui" in links:
                link = f"https://{domain}/wiki{links['webui']}"
            elif "self" in links:
                link = links["self"]
            pages.append({"title": title, "link": link})
        return pages
