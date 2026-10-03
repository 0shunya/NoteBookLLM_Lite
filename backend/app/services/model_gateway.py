from app.services.providers.base import ModelProvider
from app.services.providers.ollama_provider import OllamaProvider
from app.services.providers.response import ModelResponse


class ModelGateway:
    """
    Provider-agnostic entry point for model generation.

    The gateway does not care whether the underlying provider is
    Ollama, OpenAI, or another future provider.
    """

    def __init__(self, provider: ModelProvider):
        self.provider = provider

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
    ) -> ModelResponse:
        """
        Generate a model response through the configured provider.
        """

        return self.provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )


def create_local_gateway(
    model: str = "gemma2:2b",
) -> ModelGateway:
    """
    Create a gateway using the local Ollama provider.
    """

    provider = OllamaProvider(
        model=model,
    )

    return ModelGateway(
        provider=provider,
    )