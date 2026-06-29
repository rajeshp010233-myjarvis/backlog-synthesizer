import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, PermissionDenied, Unauthenticated
from .base import LLMProvider
from app.exceptions import NonRetryableError


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)

    def complete(self, system: str, user: str, model: str, max_tokens: int = 4000) -> str:
        try:
            m = genai.GenerativeModel(
                model_name=model,
                system_instruction=system,
            )
            resp = m.generate_content(
                user,
                generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens),
            )
            return resp.text
        except (PermissionDenied, Unauthenticated):
            raise NonRetryableError(
                "Gemini API key is invalid or missing. "
                "Check GEMINI_API_KEY in your backend/.env file."
            )
        except ResourceExhausted as e:
            if "quota" in str(e).lower() or "billing" in str(e).lower():
                raise NonRetryableError(
                    "Gemini quota exceeded — check your quota at console.cloud.google.com, then retry."
                ) from e
            raise
