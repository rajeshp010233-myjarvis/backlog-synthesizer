"""LLM provider factory.

Provider instances are created per-call to avoid shared mutable state
across concurrent pipeline runs. The underlying SDK clients are
lightweight and thread-safe.
"""
from datetime import datetime, timezone
from typing import Callable

from app.config import get_settings
from .base import LLMProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider


def get_provider(name: str) -> LLMProvider:
    """Return a provider instance by name. No global mutable cache."""
    settings = get_settings()
    if name == "anthropic":
        return AnthropicProvider()
    if name == "openai":
        return OpenAIProvider(api_key=settings.openai_api_key)
    if name == "gemini":
        return GeminiProvider(api_key=settings.google_api_key)
    if name == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url)
    raise ValueError(f"Unknown provider: {name!r}. Choose from: anthropic, openai, gemini, ollama")


def complete_for_agent(
    state: dict,
    agent_name: str,
    default_provider: str,
    default_model: str,
    system: str,
    user: str,
    max_tokens: int = 4000,
) -> tuple[str, dict]:
    """Resolve provider + model for an agent, call the LLM, return (text, trace).

    The trace contains everything needed to reproduce or audit the call:
    agent, iteration, provider, model, system_prompt, user_message,
    raw_response, approx_token counts, and a timestamp.
    """
    cfg           = state.get("agent_model_configs", {}).get(agent_name, {})
    provider_name = cfg.get("provider", default_provider)
    model         = cfg.get("model", default_model)

    text = get_provider(provider_name).complete(
        system=system, user=user, model=model, max_tokens=max_tokens
    )

    trace = {
        "agent":                agent_name,
        "call_type":            "completion",
        "iteration":            state.get("retry_count", 0),
        "provider":             provider_name,
        "model":                model,
        "system_prompt":        system,
        "user_message":         user,
        "raw_response":         text,
        "approx_input_tokens":  (len(system) + len(user)) // 4,
        "approx_output_tokens": len(text) // 4,
        "timestamp":            datetime.now(timezone.utc).isoformat(),
    }

    return text, trace


def plan_for_agent(
    state: dict,
    agent_name: str,
    default_provider: str,
    default_model: str,
    planning_system: str,
    planning_user: str,
    max_tokens: int = 1500,
) -> tuple[dict, dict]:
    """Run a dedicated planning LLM call before the agent's main execution.

    Returns (parsed_plan_dict, trace).  The plan is a structured JSON object
    the agent uses to guide its subsequent tool calls and generation.
    If JSON parsing fails the raw text is returned under plan["approach"].
    """
    from app.utils.json_utils import extract_json

    raw, trace = complete_for_agent(
        state=state,
        agent_name=agent_name,
        default_provider=default_provider,
        default_model=default_model,
        system=planning_system,
        user=planning_user,
        max_tokens=max_tokens,
    )
    trace["call_type"] = "planning"

    try:
        plan = extract_json(raw)
    except Exception:
        plan = {"approach": raw, "parse_failed": True}

    return plan, trace


def complete_with_tools_for_agent(
    state: dict,
    agent_name: str,
    default_provider: str,
    default_model: str,
    system: str,
    user: str,
    tools: list[dict],
    tool_executor: Callable[[str, dict], str],
    max_tokens: int = 4000,
) -> tuple[str, list[dict], dict]:
    """Run an LLM call with tool-use capability.

    The LLM decides which tools to call and when.  The provider runs the loop
    until the LLM produces a final answer (stop_reason != tool_calls).

    Returns (final_text, tool_calls_log, trace).
    """
    cfg           = state.get("agent_model_configs", {}).get(agent_name, {})
    provider_name = cfg.get("provider", default_provider)
    model         = cfg.get("model", default_model)

    text, tool_calls = get_provider(provider_name).complete_with_tools(
        system=system,
        user=user,
        model=model,
        tools=tools,
        tool_executor=tool_executor,
        max_tokens=max_tokens,
    )

    trace = {
        "agent":                agent_name,
        "call_type":            "tool_use",
        "iteration":            state.get("retry_count", 0),
        "provider":             provider_name,
        "model":                model,
        "system_prompt":        system,
        "user_message":         user,
        "raw_response":         text,
        "tool_calls":           tool_calls,
        "tool_calls_count":     len(tool_calls),
        "approx_input_tokens":  (len(system) + len(user)) // 4,
        "approx_output_tokens": len(text) // 4,
        "timestamp":            datetime.now(timezone.utc).isoformat(),
    }

    return text, tool_calls, trace
