from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request

from onboardai.config import load_config
from onboardai.graph import OnboardingEngine


def _http_status(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return str(response.status)
    except urllib.error.URLError as exc:
        return f"unreachable ({exc.reason})"
    except Exception as exc:  # pragma: no cover - defensive
        return f"error ({exc})"


def collect_health() -> dict[str, str]:
    config = load_config()
    engine = OnboardingEngine(config)
    health = engine.runtime_health()
    health["dataset_root"] = str(config.dataset_root)
    health["python"] = shutil.which("python3.11") or "missing"
    health["github_api"] = "configured" if config.github_token else "missing"
    health["jira_api"] = "configured" if config.atlassian_api_token else "missing"
    if engine.jira.is_available():
        projects = engine.jira.accessible_projects()
        health["jira_projects_visible"] = str(len(projects))
        if projects:
            health["jira_project_keys"] = ", ".join(project.get("key", "?") for project in projects)
        health["jira_flow_project"] = "yes" if engine.jira.project_exists(config.jira_project_key) else "no"
    health["docker_compose"] = "yes" if shutil.which("docker") else "no"
    health["qdrant_http"] = _http_status(f"{config.qdrant_url.rstrip('/')}/readyz")
    if shutil.which("docker"):
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            check=False,
            capture_output=True,
            text=True,
        )
        health["docker_compose_ps"] = _summarize_compose_ps(result.stdout, result.stderr)
    return health


def _summarize_compose_ps(stdout: str, stderr: str) -> str:
    if not stdout.strip():
        return stderr.strip() or "no output"
    services: list[str] = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return stdout.strip()
        services.append(f"{payload.get('Service', 'unknown')}={payload.get('State', 'unknown')}")
    return ", ".join(services) if services else "no output"


def main() -> None:
    print(json.dumps(collect_health(), indent=2))


if __name__ == "__main__":  # pragma: no cover - manual use
    main()
