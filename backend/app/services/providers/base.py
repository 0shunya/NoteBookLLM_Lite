from abc import ABC, abstractmethod

from app.services.providers.response import ModelResponse


class ModelProvider(ABC):
    """
    Common interface that every LLM provider must implement.
    """

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
    ) -> ModelResponse:
        raise NotImplementedError