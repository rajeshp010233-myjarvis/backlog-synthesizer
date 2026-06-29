from abc import ABC, abstractmethod
from typing import Callable


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, model: str, max_tokens: int = 4000) -> str: ...

    def complete_with_tools(
        self,
        system: str,
        user: str,
        model: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], str],
        max_tokens: int = 4000,
    ) -> tuple[str, list[dict]]:
        """Run an LLM call with tool-use capability.

        Returns (final_text, tool_calls_log).
        Default implementation ignores tools and falls back to plain complete()
        so Gemini/Ollama providers don't break.
        """
        text = self.complete(system=system, user=user, model=model, max_tokens=max_tokens)
        return text, []
