from __future__ import annotations

from onboardai.config import AppConfig
from onboardai.llm_backend import LLMBackend


class LocalResponder:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._llm_backend = LLMBackend(config)

    def is_enabled(self) -> bool:
        if self._llm_backend.is_enabled():
            return True
        return self.config.llm_backend == "ollama"

    def answer(self, question: str, context: str) -> str | None:
        # Try Groq/Mistral first
        if self._llm_backend.is_enabled():
            result = self._llm_backend.answer(question, context)
            if result:
                return result

        # Fallback to Ollama
        if self.config.llm_backend != "ollama":
            return None
        try:
            import ollama
        except ImportError:
            return None
        try:
            client = ollama.Client(host=self.config.ollama_host)
            response = client.chat(
                model=self.config.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Answer only from the supplied onboarding context. "
                            "If the context is insufficient, say so explicitly."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Question:\n{question}\n\nContext:\n{context}",
                    },
                ],
            )
            return response["message"]["content"].strip()
        except Exception:
            return None
