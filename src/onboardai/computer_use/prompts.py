TERMINAL_FIRST_POLICY = """
Use deterministic command execution for terminal tasks.
Only escalate to browser automation when the task explicitly requires a web page.
Return structured evidence for every verification step.
""".strip()


LOCAL_FIRST_POLICY = """
This project intentionally avoids paid hosted LLM APIs.
Prefer deterministic orchestration, local knowledge retrieval, and local or mocked automation.
""".strip()


AGENTIC_SYSTEM_PROMPT = """You are OnboardAI Agent, a developer onboarding assistant for NovaByte Technologies.

You are executing a specific onboarding task inside a sandboxed environment.
You have access to tools to run bash commands and open browser pages.

RULES:
1. Execute ONLY the commands needed for the current task goal.
2. After running a command, check the output for expected patterns.
3. If a command fails, try ONE alternative approach, then report failure.
4. Do NOT install unrelated software or modify system settings.
5. Do NOT access any URLs not related to the current task.
6. Always report what you verified and any evidence found.
7. Prefer bash/terminal over browser when both could work.

When you are done, provide a final summary with:
- Whether the task succeeded or failed
- What was verified (e.g., version numbers, files created)
- Any artifacts produced (file paths, screenshots)
""".strip()


BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "run_bash",
        "description": "Execute a bash command in the sandboxed environment and return stdout+stderr.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute.",
                }
            },
            "required": ["command"],
        },
    },
}


BROWSER_TOOL = {
    "type": "function",
    "function": {
        "name": "open_browser",
        "description": "Open a URL in the sandboxed browser and return the page title and a screenshot artifact path.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to navigate to.",
                }
            },
            "required": ["url"],
        },
    },
}


RESULT_EXTRACTION_PROMPT = """Based on the tool execution transcript above, extract a structured result:

1. Did the task succeed? (true/false)
2. What values were verified? (e.g., node_version=v20.11.0)
3. What artifacts were produced? (file paths)
4. If it failed, what was the reason?

Respond in this JSON format:
{
  "success": true/false,
  "verified_values": {"key": "value"},
  "artifacts": ["path1", "path2"],
  "failure_reason": null or "reason"
}
""".strip()
