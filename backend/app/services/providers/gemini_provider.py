"""Gemini API adapter using Google's GenerateContent REST endpoint."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.services.providers.base import ModelProvider
from app.services.providers.response import ModelResponse


class GeminiProvider(ModelProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 120):
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is required when MODEL_PROVIDER=gemini. "
                "Add it to the local .env file, then restart the API."
            )
        if not model.strip():
            raise ValueError("GEMINI_MODEL must not be empty.")
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
    ) -> ModelResponse:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(self.model, safe='.-')}:generateContent"
        )
        body = json.dumps(
            {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {"temperature": temperature},
            }
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

        started = time.perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            message = self._error_message(exc.read())
            safe_message = message.replace(self.api_key, "[redacted]")
            raise RuntimeError(
                f"Gemini API returned HTTP {exc.code}: {safe_message[:400]}"
            ) from None
        except URLError as exc:
            raise RuntimeError(f"Could not connect to the Gemini API: {exc.reason}") from None
        except TimeoutError:
            raise RuntimeError(
                f"Gemini API timed out after {self.timeout_seconds} seconds."
            ) from None

        latency_ms = int((time.perf_counter() - started) * 1000)
        candidates = payload.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        answer = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and not part.get("thought")
        ).strip()
        if not answer:
            block_reason = payload.get("promptFeedback", {}).get("blockReason")
            reason = f" (block reason: {block_reason})" if block_reason else ""
            raise RuntimeError(f"Gemini returned no answer text{reason}.")

        usage = payload.get("usageMetadata") or {}
        return ModelResponse(
            answer=answer,
            provider=self.name,
            model=payload.get("modelVersion", self.model),
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
            latency_ms=latency_ms,
        )

    @staticmethod
    def _error_message(body: bytes) -> str:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "The provider returned an unreadable error response."
        error = payload.get("error", {})
        return str(error.get("message") or "The provider rejected the request.")
