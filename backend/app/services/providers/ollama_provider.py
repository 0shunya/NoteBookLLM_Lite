import time

from ollama import Client

from app.config import settings
from app.services.providers.base import ModelProvider
from app.services.providers.response import ModelResponse


class OllamaProvider(ModelProvider):
    """Local chat completion provider backed by Ollama."""

    name = "ollama"

    def __init__(self, model: str | None = None):
        self.model = model or settings.generation_model
        self.client = Client(host=settings.ollama_host)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
    ) -> ModelResponse:
        started = time.perf_counter()
        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": temperature},
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        answer = response["message"]["content"].strip()
        if not answer:
            raise RuntimeError("The Ollama model returned an empty answer.")
        return ModelResponse(
            answer=answer,
            provider=self.name,
            model=self.model,
            input_tokens=response.get("prompt_eval_count"),
            output_tokens=response.get("eval_count"),
            latency_ms=latency_ms,
        )
