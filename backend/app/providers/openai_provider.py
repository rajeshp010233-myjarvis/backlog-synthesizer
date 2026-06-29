import json
from typing import Callable

from openai import OpenAI, RateLimitError, AuthenticationError

from .base import LLMProvider
from app.exceptions import NonRetryableError

_MAX_TOOL_CALLS = 15   # safety cap — prevents runaway tool loops


class OpenAIProvider(LLMProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        kwargs = {}
        if base_url:
            kwargs["base_url"] = base_url
        if api_key:
            kwargs["api_key"] = api_key
        self._client = OpenAI(**kwargs)

    def complete(self, system: str, user: str, model: str, max_tokens: int = 4000) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
            )
            return resp.choices[0].message.content or ""
        except AuthenticationError:
            raise NonRetryableError(
                "OpenAI API key is invalid or missing. "
                "Check OPENAI_API_KEY in your backend/.env file."
            )
        except RateLimitError as e:
            if "insufficient_quota" in str(e):
                raise NonRetryableError(
                    "OpenAI quota exceeded — your account has no remaining credits. "
                    "Add credits at platform.openai.com/account/billing, then retry."
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
        """Run a tool-use loop: LLM decides which tools to call and when."""
        try:
            messages: list[dict] = [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ]
            tool_calls_log: list[dict] = []
            calls_made = 0

            while calls_made < _MAX_TOOL_CALLS:
                resp = self._client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
                choice = resp.choices[0]
                msg   = choice.message

                if choice.finish_reason == "tool_calls" and msg.tool_calls:
                    # Append assistant message with tool_calls (required by OpenAI)
                    messages.append({
                        "role":       "assistant",
                        "content":    msg.content or "",
                        "tool_calls": [
                            {
                                "id":       tc.id,
                                "type":     "function",
                                "function": {
                                    "name":      tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    })
                    # Execute each tool and append results
                    for tc in msg.tool_calls:
                        args   = json.loads(tc.function.arguments)
                        result = tool_executor(tc.function.name, args)
                        tool_calls_log.append({
                            "tool":           tc.function.name,
                            "args":           args,
                            "result_preview": str(result)[:300],
                        })
                        messages.append({
                            "role":         "tool",
                            "tool_call_id": tc.id,
                            "content":      str(result),
                        })
                        calls_made += 1
                else:
                    return msg.content or "", tool_calls_log

            # Safety: hit tool call limit — ask for final answer without tools
            messages.append({
                "role":    "user",
                "content": "You have reached the tool call limit. Please produce your final answer now based on what you have gathered.",
            })
            resp = self._client.chat.completions.create(
                model=model, max_tokens=max_tokens, messages=messages
            )
            return resp.choices[0].message.content or "", tool_calls_log

        except AuthenticationError:
            raise NonRetryableError(
                "OpenAI API key is invalid or missing. "
                "Check OPENAI_API_KEY in your backend/.env file."
            )
        except RateLimitError as e:
            if "insufficient_quota" in str(e):
                raise NonRetryableError(
                    "OpenAI quota exceeded. Add credits at platform.openai.com/account/billing."
                ) from e
            raise
