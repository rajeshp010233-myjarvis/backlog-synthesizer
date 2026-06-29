from .openai_provider import OpenAIProvider


class OllamaProvider(OpenAIProvider):
    """Ollama exposes an OpenAI-compatible API; reuse OpenAIProvider with local base URL."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        super().__init__(base_url=f"{base_url}/v1", api_key="ollama")
