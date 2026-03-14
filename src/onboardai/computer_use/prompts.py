TERMINAL_FIRST_POLICY = """
Use deterministic command execution for terminal tasks.
Only escalate to browser automation when the task explicitly requires a web page.
Return structured evidence for every verification step.
""".strip()


LOCAL_FIRST_POLICY = """
This project intentionally avoids paid hosted LLM APIs.
Prefer deterministic orchestration, local knowledge retrieval, and local or mocked automation.
""".strip()
