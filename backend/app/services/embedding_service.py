"""Local embeddings through the configured Ollama model."""

from dataclasses import dataclass
import time

from ollama import Client

from app.config import settings


EMBEDDING_MODEL = settings.embedding_model
client = Client(host=settings.ollama_host)


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    input_tokens: int | None
    latency_ms: int


def generate_embedding_batch(texts: list[str]) -> EmbeddingBatch:
    if not texts or any(not text.strip() for text in texts):
        raise ValueError("Embedding input must contain non-empty text.")

    started = time.perf_counter()
    response = client.embed(model=EMBEDDING_MODEL, input=texts)
    vectors = response["embeddings"]
    if len(vectors) != len(texts):
        raise RuntimeError("Ollama returned a different number of embeddings than requested.")

    for vector in vectors:
        if len(vector) != settings.embedding_dimensions:
            raise ValueError(
                f"Expected {settings.embedding_dimensions} embedding dimensions, received {len(vector)}."
            )
    return EmbeddingBatch(
        vectors=[list(vector) for vector in vectors],
        input_tokens=response.get("prompt_eval_count"),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    return generate_embedding_batch(texts).vectors


def generate_embedding(text: str) -> list[float]:
    if not text or not text.strip():
        raise ValueError("Cannot generate an embedding for empty text.")
    return generate_embeddings([text])[0]
