"""LLM provider abstraction.

The application never couples to a specific vendor. Add OpenAI / Anthropic /
Groq / OpenRouter by implementing LLMProvider and registering it here.
"""
from __future__ import annotations

import abc

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("ai.provider")


class LLMUnavailable(RuntimeError):
    """Raised when the configured LLM cannot be reached / is not configured."""


class LLMProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def generate(self, system: str, prompt: str, *, json_mode: bool = False,
                 temperature: float = 0.2) -> str:
        ...

    @property
    @abc.abstractmethod
    def available(self) -> bool:
        ...


_provider_singleton: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton

    provider_name = settings.llm_provider.lower()
    if provider_name == "gemini":
        from app.ai.gemini import GeminiProvider
        _provider_singleton = GeminiProvider()
    else:
        logger.warning("Unknown LLM provider '%s'; AI features disabled.", provider_name)
        _provider_singleton = _NullProvider()
    return _provider_singleton


class _NullProvider(LLMProvider):
    name = "null"

    def generate(self, system, prompt, *, json_mode=False, temperature=0.2):
        raise LLMUnavailable("No LLM provider is configured.")

    @property
    def available(self) -> bool:
        return False
