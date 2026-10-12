"""One entry point for all text-generation provider calls."""

import os

from app.config import settings
from app.services.providers.base import ModelProvider
from app.services.providers.ollama_provider import OllamaProvider
from app.services.providers.response import ModelResponse


class ModelGateway:
    def __init__(self, provider: ModelProvider):
        self.provider = provider

    @property
    def provider_name(self) -> str:
        return self.provider.name

    @property
    def model_name(self) -> str:
        return self.provider.model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
    ) -> ModelResponse:
        return self.provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )


def create_model_gateway(
    provider_name: str | None = None,
    model: str | None = None,
) -> ModelGateway:
    selected_provider = (provider_name or settings.model_provider).lower()
    if selected_provider == "ollama":
        return ModelGateway(OllamaProvider(model=model or settings.generation_model))
    if selected_provider == "openai":
        from app.services.providers.openai_provider import OpenAIProvider

        return ModelGateway(
            OpenAIProvider(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                model=model or settings.openai_model,
            )
        )
    if selected_provider == "gemini":
        from app.services.providers.gemini_provider import GeminiProvider

        return ModelGateway(
            GeminiProvider(
                api_key=os.getenv("GEMINI_API_KEY", ""),
                model=model or settings.gemini_model,
            )
        )
    raise ValueError(f"Unsupported model provider: {selected_provider}")


def create_local_gateway(model: str | None = None) -> ModelGateway:
    """Backward-compatible factory pinned to the local Ollama provider."""
    return create_model_gateway(provider_name="ollama", model=model)
