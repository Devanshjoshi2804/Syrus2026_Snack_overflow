from __future__ import annotations

import base64
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from onboardai.config import AppConfig
from onboardai.models import SandboxSession


class SandboxManager(ABC):
    @abstractmethod
    def start(self) -> SandboxSession:
        raise NotImplementedError

    @abstractmethod
    def run_command(self, session: SandboxSession, command: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def screenshot(self, session: SandboxSession) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def open_url(self, session: SandboxSession, url: str) -> str:
        raise NotImplementedError


class MockSandboxManager(SandboxManager):
    def start(self) -> SandboxSession:
        return SandboxSession(
            session_id="mock-sandbox",
            stream_url="https://example.invalid/mock-novnc",
            backend="mock",
            metadata={"node_version": "v20.11.0", "pnpm_version": "8.15.0"},
        )

    def run_command(self, session: SandboxSession, command: str) -> str:
        lowered = command.lower()
        if "nvm install 20" in lowered:
            session.metadata["node_version"] = "v20.11.0"
            return "Downloading and installing node v20.11.0...\nNow using node v20.11.0"
        if "node --version" in lowered:
            return session.metadata.get("node_version", "v20.11.0")
        if "python3.11 --version" in lowered:
            session.metadata["python_version"] = "Python 3.11.11"
            return session.metadata["python_version"]
        if "npm install -g pnpm@8" in lowered:
            session.metadata["pnpm_version"] = "8.15.0"
            return "added 1 package in 2s"
        if "pnpm --version" in lowered:
            return session.metadata.get("pnpm_version", "8.15.0")
        if "pnpm install" in lowered:
            return "Lockfile is up to date\nDone in 1.9s"
        if "pnpm dev" in lowered:
            return "VITE v5.4.0  ready in 120 ms\nLocal: http://localhost:5173/"
        if "pnpm test" in lowered:
            return "PASS src/app.test.ts\nTest Suites: 1 passed"
        if "pnpm storybook" in lowered:
            return "Storybook 8.2.0 started on http://localhost:6006/"
        if "tsc --version" in lowered:
            return "Version 5.6.3"
        if "poetry --version" in lowered:
            session.metadata["poetry_version"] = "Poetry (version 1.8.4)"
            return session.metadata["poetry_version"]
        if "install.python-poetry.org" in lowered:
            session.metadata["poetry_version"] = "Poetry (version 1.8.4)"
            return "Retrieving Poetry metadata\nInstalling Poetry (1.8.4)"
        if "poetry install" in lowered:
            return "Installing dependencies from lock file\nPackage operations: 42 installs"
        if "poetry run pytest" in lowered or lowered.strip() == "pytest" or " pytest" in lowered:
            return "=================== 18 passed in 4.21s ==================="
        if "uvicorn" in lowered:
            return "Uvicorn running on http://127.0.0.1:8000"
        if "git clone " in lowered:
            parts = command.split()
            source = parts[2] if len(parts) > 2 else "https://github.com/example/demo-repo.git"
            repo_name = source.rstrip("/").split("/")[-1].replace(".git", "")
            target_dir = parts[3] if len(parts) > 3 else repo_name
            session.metadata["last_cloned_repo"] = repo_name
            session.metadata["last_clone_dir"] = target_dir
            return f"Cloning into '{target_dir}'...\nReceiving objects: 100%\n{repo_name}"
        if lowered.startswith("ls "):
            repo_name = session.metadata.get("last_cloned_repo", "demo-repo")
            return f"README.md\nsrc\npackage.json\n{repo_name}"
        if "git checkout -b " in lowered:
            branch_name = command.split("git checkout -b", 1)[1].strip()
            session.metadata["current_branch"] = branch_name
            return f"Switched to a new branch '{branch_name}'"
        if "git branch --show-current" in lowered:
            return session.metadata.get("current_branch", "main")
        if "git config --global user.name" in lowered:
            session.metadata["git_name"] = command.split("git config --global user.name", 1)[1].strip().strip('"')
            return ""
        if "git config --global user.email" in lowered:
            if lowered.strip() == "git config --global user.email":
                return session.metadata.get("git_email", "new.hire@novabyte.dev")
            session.metadata["git_email"] = command.split("git config --global user.email", 1)[1].strip().strip('"')
            return session.metadata.get("git_email", "new.hire@novabyte.dev")
        if "terraform version" in lowered:
            return "Terraform v1.9.8"
        if "kubectl version --client" in lowered:
            return "Client Version: v1.31.2"
        if "helm version" in lowered:
            return "version.BuildInfo{Version:\"v3.16.2\"}"
        if "terraform fmt -check" in lowered:
            return "All Terraform files are properly formatted"
        if "docker compose ps" in lowered:
            return "NAME                STATUS\nqdrant              Up 2 minutes"
        if "echo" in lowered:
            return command.split("echo", 1)[1].strip()
        return f"Mock executed: {command}"

    def screenshot(self, session: SandboxSession) -> bytes:
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9uTHXZgAAAABJRU5ErkJggg=="
        )

    def open_url(self, session: SandboxSession, url: str) -> str:
        session.metadata["last_url"] = url
        return f"Opened {url}"


class RealE2BSandboxManager(SandboxManager):
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._sandbox = None

    def start(self) -> SandboxSession:
        try:
            from e2b_desktop import Sandbox
        except ImportError as exc:
            raise RuntimeError("e2b-desktop is not installed") from exc
        self._sandbox = Sandbox.create(api_key=self.config.e2b_api_key)
        stream_url = None
        stream = getattr(self._sandbox, "stream", None)
        if stream is not None:
            starter = getattr(stream, "start", None)
            if callable(starter):
                started = starter()
                stream_url = getattr(started, "url", None) or getattr(stream, "url", None)
        sandbox_id = getattr(self._sandbox, "sandbox_id", None) or getattr(self._sandbox, "id", "e2b")
        return SandboxSession(
            session_id=str(sandbox_id),
            stream_url=stream_url,
            backend="e2b",
        )

    def run_command(self, session: SandboxSession, command: str) -> str:
        if self._sandbox is None:
            raise RuntimeError("Sandbox has not been started")
        runner = getattr(self._sandbox, "commands", None)
        if runner and hasattr(runner, "run"):
            result = runner.run(command, timeout=self.config.e2b_timeout_seconds)
            stdout = getattr(result, "stdout", "") or ""
            stderr = getattr(result, "stderr", "") or ""
            return f"{stdout}\n{stderr}".strip()
        process = self._sandbox.run(command)
        return getattr(process, "stdout", "") or ""

    def screenshot(self, session: SandboxSession) -> bytes:
        if self._sandbox is None:
            raise RuntimeError("Sandbox has not been started")
        desktop = getattr(self._sandbox, "desktop", self._sandbox)
        shot = desktop.screenshot()
        if isinstance(shot, bytes):
            return shot
        if hasattr(shot, "data"):
            return shot.data
        if hasattr(shot, "save"):
            tmp_path = Path(".cache") / "e2b_screenshot.png"
            tmp_path.parent.mkdir(exist_ok=True)
            shot.save(tmp_path)
            return tmp_path.read_bytes()
        raise RuntimeError("Unexpected screenshot response from E2B")

    def open_url(self, session: SandboxSession, url: str) -> str:
        if self._sandbox is None:
            raise RuntimeError("Sandbox has not been started")
        desktop = getattr(self._sandbox, "desktop", self._sandbox)
        browser = getattr(desktop, "browser", None)
        if browser and hasattr(browser, "open"):
            browser.open(url)
            return f"Opened {url}"
        self.run_command(session, f"python3 -m webbrowser '{url}'")
        return f"Opened {url}"


class LocalShellSandboxManager(SandboxManager):
    def start(self) -> SandboxSession:
        return SandboxSession(session_id="local-shell", backend="local")

    def run_command(self, session: SandboxSession, command: str) -> str:
        result = subprocess.run(
            command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
        return f"{result.stdout}\n{result.stderr}".strip()

    def screenshot(self, session: SandboxSession) -> bytes:
        return b""

    def open_url(self, session: SandboxSession, url: str) -> str:
        subprocess.run(["open", url], check=False)
        return f"Opened {url}"


def build_sandbox_manager(config: AppConfig) -> SandboxManager:
    if config.mode.value == "demo_real" and config.e2b_api_key:
        try:
            return RealE2BSandboxManager(config)
        except Exception:
            return MockSandboxManager()
    return MockSandboxManager()
