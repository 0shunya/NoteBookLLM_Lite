from dataclasses import dataclass


@dataclass
class ModelResponse:
    """
    Standard response returned by every model provider.

    This keeps provider-specific response formats out of the
    rest of the application.
    """

    answer: str
    provider: str
    model: str

    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None