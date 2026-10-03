"""Google Gemini provider. Model name is configurable via GEMINI_MODEL."""
from __future__ import annotations

from app.ai.provider import LLMProvider, LLMUnavailable
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("ai.gemini")


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self) -> None:
        self._model = None
        self._configured = False

    def _ensure(self):
        if self._configured:
            return
        if not settings.gemini_api_key:
            raise LLMUnavailable("GEMINI_API_KEY is not set.")
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailable("google-generativeai is not installed.") from exc
        genai.configure(api_key=settings.gemini_api_key)
        self._genai = genai
        self._configured = True

    @property
    def available(self) -> bool:
        return bool(settings.gemini_api_key)

    def generate(self, system: str, prompt: str, *, json_mode: bool = False,
                 temperature: float = 0.2) -> str:
        self._ensure()
        generation_config = {
            "temperature": temperature,
            "response_mime_type": "application/json" if json_mode else "text/plain",
        }
        try:
            model = self._genai.GenerativeModel(
                settings.gemini_model,
                system_instruction=system,
                generation_config=generation_config,
            )
            resp = model.generate_content(prompt)
            return (resp.text or "").strip()
        except Exception as exc:  # network / quota / model errors
            logger.error("Gemini request failed: %s", exc)
            raise LLMUnavailable(str(exc)) from exc
