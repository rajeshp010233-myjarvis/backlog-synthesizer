from typing import Callable

from anthropic import Anthropic, AuthenticationError, PermissionDeniedError, RateLimitError

from .base import LLMProvider
from app.exceptions import NonRetryableError

_MAX_TOOL_CALLS = 15


class AnthropicProvider(LLMProvider):
    def __init__(self):
        self._client = Anthropic()

    def complete(self, system: str, user: str, model: str, max_tokens: int = 4000) -> str:
        try:
            resp = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text
        except (AuthenticationError, PermissionDeniedError):
            raise NonRetryableError(
                "Anthropic API key is invalid or missing. "
                "Check ANTHROPIC_API_KEY in your backend/.env file."
            )
        except RateLimitError as e:
            if "credit" in str(e).lower() or "quota" in str(e).lower():
                raise NonRetryableError(
                    "Anthropic quota exceeded — your account has no remaining credits. "
                    "Add credits at console.anthropic.com, then retry."
                ) from e
            raise

    def complete_with_tools(
        self,
        system: str,
        user: str,
        model: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], str],
        max_tokens: int = 4000,
    ) -> tuple[str, list[dict]]:
        """Run a tool-use loop using Anthropic's tool_use stop reason."""
        from app.tools.agent_tools import to_anthropic_tools
        try:
            anthropic_tools = to_anthropic_tools(tools)
            messages: list[dict] = [{"role": "user", "content": user}]
            tool_calls_log: list[dict] = []
            calls_made = 0

            while calls_made < _MAX_TOOL_CALLS:
                resp = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                    tools=anthropic_tools,
                )

                if resp.stop_reason == "tool_use":
                    # Append assistant turn with tool_use blocks
                    messages.append({"role": "assistant", "content": resp.content})

                    # Execute each tool_use block and collect results
                    tool_results = []
                    for block in resp.content:
                        if block.type == "tool_use":
                            result = tool_executor(block.name, block.input)
                            tool_calls_log.append({
                                "tool":           block.name,
                                "args":           block.input,
                                "result_preview": str(result)[:300],
                            })
                            tool_results.append({
                                "type":        "tool_result",
                                "tool_use_id": block.id,
                                "content":     str(result),
                            })
                            calls_made += 1

                    messages.append({"role": "user", "content": tool_results})
                else:
                    text = next(
                        (b.text for b in resp.content if hasattr(b, "text")), ""
                    )
                    return text, tool_calls_log

            # Hit limit — ask for final answer
            messages.append({
                "role":    "user",
                "content": "You have reached the tool call limit. Please produce your final answer now based on what you have gathered.",
            })
            resp = self._client.messages.create(
                model=model, max_tokens=max_tokens, system=system, messages=messages
            )
            text = next((b.text for b in resp.content if hasattr(b, "text")), "")
            return text, tool_calls_log

        except (AuthenticationError, PermissionDeniedError):
            raise NonRetryableError(
                "Anthropic API key is invalid or missing. "
                "Check ANTHROPIC_API_KEY in your backend/.env file."
            )
        except RateLimitError as e:
            if "credit" in str(e).lower() or "quota" in str(e).lower():
                raise NonRetryableError(
                    "Anthropic quota exceeded. Add credits at console.anthropic.com."
                ) from e
            raise
