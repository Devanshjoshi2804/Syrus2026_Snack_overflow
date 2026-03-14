from __future__ import annotations

import argparse
import json
from pathlib import Path

from onboardai.adapters.jira import JiraAdapter
from onboardai.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Jira starter issues from the dataset.")
    parser.add_argument(
        "--project-key",
        help="Override the Jira project key. If omitted, the adapter uses FLOW or the only visible project.",
    )
    parser.add_argument(
        "--starter-ticket-path",
        default="datset/starter_tickets.md",
        help="Path to the starter tickets markdown file.",
    )
    args = parser.parse_args()

    config = load_config()
    adapter = JiraAdapter(config)
    result = adapter.seed_starter_issues(
        Path(args.starter_ticket_path),
        project_key=args.project_key,
    )
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":  # pragma: no cover - manual use
    main()
