from __future__ import annotations

from onboardai.adapters.browser import MockBrowserAdapter
from onboardai.adapters.e2b import MockSandboxManager
from onboardai.computer_use.worker import ComputerUseWorker
from onboardai.config import AppConfig
from onboardai.models import ComputerUseInstruction


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
