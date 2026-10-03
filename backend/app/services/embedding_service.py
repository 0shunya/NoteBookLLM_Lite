from ollama import Client


# Ollama runs locally on the developer machine.
OLLAMA_HOST = "http://localhost:11434"

# Embedding model used by NotebookLM Lite.
EMBEDDING_MODEL = "nomic-embed-text"


client = Client(
    host=OLLAMA_HOST,
)


def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for a piece of text using Ollama.

    Keeping this operation behind one function means the rest of
    the application does not need to know which embedding provider
    is being used.
    """

    if not text or not text.strip():
        raise ValueError("Cannot generate an embedding for empty text.")

    response = client.embed(
        model=EMBEDDING_MODEL,
        input=text,
    )

    embedding = response["embeddings"][0]

    if len(embedding) != 768:
        raise ValueError(
            f"Unexpected embedding dimension: {len(embedding)}"
        )

    return embedding