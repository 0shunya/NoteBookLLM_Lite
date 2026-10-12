"""Optional OpenAI adapter; local Ollama remains the default provider."""

import time

from openai import OpenAI

from app.services.providers.base import ModelProvider
from app.services.providers.response import ModelResponse


class OpenAIProvider(ModelProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str):
        if not api_key or not model:
            raise ValueError("Both an OpenAI API key and model are required.")
        self.model = model
        self.client = OpenAI(api_key=api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
    ) -> ModelResponse:
        started = time.perf_counter()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        answer = response.choices[0].message.content
        if not answer:
            raise RuntimeError("The OpenAI model returned an empty answer.")
        usage = response.usage
        return ModelResponse(
            answer=answer.strip(),
            provider=self.name,
            model=self.model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
            latency_ms=latency_ms,
        )
