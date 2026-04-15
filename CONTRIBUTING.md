# Contributing to devjournal

## Adding a New Collector

Every data source (Jira, GitHub, etc.) is a **collector**. Adding one takes three steps.

### 1. Create the collector file

Create `src/devjournal/collectors/your_source.py`:

```python
from __future__ import annotations

import logging
from datetime import date

from devjournal.collector import Collector, CollectorResult

log = logging.getLogger("devjournal")


class YourSourceCollector(Collector):
    name = "your_source"           # human-readable name
    config_key = "your_source"     # matches the key in config.yaml

    def collect(self, target_date: date, config: dict) -> CollectorResult:
        # `config` contains the merged global + collector-specific config.
        # Fetch your data here.
        items = []  # list of dicts — shape is up to you

        return CollectorResult(
            section_id="your_source",          # unique section ID for the note
            heading="### Your Source",          # markdown heading
            items=items,
            empty_message="No activity today.",
        )

    def collect_agenda(self, target_date: date, config: dict) -> CollectorResult | None:
        # Optional: return morning-agenda data, or None.
        return None
```

### 2. Register it

Add your import to `src/devjournal/collectors/__init__.py`:

```python
from devjournal.collectors import (
    # ... existing imports ...
    your_source,
)
```

### 3. Add a formatter (if needed)

If your items need custom rendering, add a renderer in `src/devjournal/formatter.py`:

```python
def _render_your_source(result: CollectorResult) -> str:
    # Return a markdown string
    ...

_RENDERERS["your_source"] = _render_your_source
```

Otherwise the generic renderer will create a bullet list from `title` and `link` fields.

### 4. Add config documentation

Add a section to `config.example.yaml`:

```yaml
  your_source:
    enabled: false
    api_key: ""
```

### 5. Write tests

Create `tests/collectors/test_your_source.py`. Use the `responses` library to mock HTTP calls:

```python
import responses
from devjournal.collectors.your_source import YourSourceCollector

@responses.activate
def test_collect_returns_items(sample_config):
    responses.get("https://api.example.com/...", json={...})
    collector = YourSourceCollector()
    result = collector.collect(date(2026, 4, 15), {...})
    assert len(result.items) > 0
```

Run `pytest` to verify.

## Development Setup

```bash
git clone https://github.com/vedanthvasudev/devjournal.git
cd devjournal
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src/ tests/
```

## Code Style

- Python 3.10+ (use `from __future__ import annotations`)
- Formatted with `ruff`
- Type hints encouraged but not mandatory
- Tests for every collector

## Pull Requests

- One feature per PR
- Include tests
- Update README if adding a new integration
