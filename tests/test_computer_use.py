from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from onboardai.adapters.browser import MockBrowserAdapter
from onboardai.adapters.e2b import LocalShellSandboxManager, MockSandboxManager, build_sandbox_manager
from onboardai.computer_use.worker import AgenticComputerUseWorker, ComputerUseWorker, build_worker
from onboardai.config import AppConfig
from onboardai.models import RunMode
from onboardai.models import ComputerUseInstruction
from onboardai.app import _machine_content
from onboardai.graph import OnboardingEngine


def test_computer_use_worker_verifies_node_version(project_root):
    config = AppConfig(project_root=project_root)
    sandbox = MockSandboxManager()
    worker = ComputerUseWorker(config, sandbox, MockBrowserAdapter())
    session = sandbox.start()
    instruction = ComputerUseInstruction(
        task_id="BI-01",
        goal="Install Node.js 20 via nvm",
        success_criteria=["node installed"],
        expected_patterns={"node_version": r"v20\.\d+\.\d+"},
        command_plan=[
            'export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm install 20',
            'export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && node --version',
        ],
    )
    result = worker.execute(instruction, session)
    assert result.success is True
    assert result.verified_values["node_version"].startswith("v20.")


def test_computer_use_worker_uses_mock_browser(project_root):
    config = AppConfig(project_root=project_root)
    sandbox = MockSandboxManager()
    worker = ComputerUseWorker(config, sandbox, MockBrowserAdapter())
    session = sandbox.start()
    result = worker.execute(
        ComputerUseInstruction(
            task_id="C-07",
            goal="Open GitHub org page",
            success_criteria=["page opened"],
            url="https://github.com/novabyte-demo",
        ),
        session,
    )
    assert result.success is True
    assert result.verified_values["url"] == "https://github.com/novabyte-demo"


def test_dev_mock_mode_forces_deterministic_worker(project_root):
    config = AppConfig(
        project_root=project_root,
        mode=RunMode.DEV_MOCK,
        llm_backend="groq",
        groq_api_key="test-key",
    )
    worker = build_worker(config, MockSandboxManager(), MockBrowserAdapter(), MagicMock(is_enabled=lambda: True))
    assert isinstance(worker, ComputerUseWorker)
    assert not isinstance(worker, AgenticComputerUseWorker)


def test_local_sandbox_backend_builds_isolated_workbench(project_root):
    config = AppConfig(project_root=project_root, sandbox_backend="local")
    sandbox = build_sandbox_manager(config)
    assert isinstance(sandbox, LocalShellSandboxManager)
    session = sandbox.start()
    assert session.backend == "local"
    assert "work_dir" in session.metadata


def test_browser_activity_updates_local_workbench_metadata(project_root):
    config = AppConfig(project_root=project_root, sandbox_backend="local")
    sandbox = LocalShellSandboxManager(config)
    worker = ComputerUseWorker(config, sandbox, MockBrowserAdapter())
    session = sandbox.start()

    result = worker.execute(
        ComputerUseInstruction(
            task_id="C-07",
            goal="Open GitHub org page",
            success_criteria=["page opened"],
            url="https://github.com/NovaByte-Technologies",
        ),
        session,
    )

    assert result.success is True
    assert session.metadata["last_url"] == "https://github.com/NovaByte-Technologies"
    assert session.metadata["last_command"] == "open https://github.com/NovaByte-Technologies"
    assert "Opened https://github.com/NovaByte-Technologies" in session.metadata["last_output"]


def test_machine_content_renders_local_workbench(project_root):
    config = AppConfig(project_root=project_root, sandbox_backend="local", browser_backend="mock")
    engine = OnboardingEngine(config)
    state = engine.new_state()
    work_dir = state.sandbox_session.metadata["work_dir"]
    (config.project_root / ".cache").mkdir(exist_ok=True)
    (Path(work_dir) / "connector-runtime-demo").mkdir(exist_ok=True)

    content = _machine_content(state)

    assert "## Local Machine" in content
    assert "isolated local workbench" in content
    assert "connector-runtime-demo/" in content


def test_local_sandbox_does_not_append_mock_fallback_output(project_root):
    config = AppConfig(project_root=project_root, sandbox_backend="local")
    sandbox = LocalShellSandboxManager(config)
    session = sandbox.start()

    output = sandbox.run_command(session, "this-command-should-not-exist")

    assert "fallback simulated" not in output
