import time

from ollama import Client

from app.services.providers.base import ModelProvider
from app.services.providers.response import ModelResponse


OLLAMA_HOST = "http://localhost:11434"


class OllamaProvider(ModelProvider):
    """
    Ollama implementation of the ModelProvider interface.
    """

    def __init__(self, model: str):
        self.model = model
        self.client = Client(host=OLLAMA_HOST)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
    ) -> ModelResponse:
        """
        Generate a response using Ollama and normalize the result
        into our common ModelResponse structure.
        """

        start_time = time.perf_counter()

        response = self.client.chat(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            options={
                "temperature": temperature,
            },
        )

        latency_ms = int(
            (time.perf_counter() - start_time) * 1000
        )

        answer = response["message"]["content"].strip()

        if not answer:
            raise RuntimeError(
                "The Ollama model returned an empty answer."
            )

        # Ollama exposes usage information on supported responses.
        input_tokens = response.get("prompt_eval_count")
        output_tokens = response.get("eval_count")

        return ModelResponse(
            answer=answer,
            provider="ollama",
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )