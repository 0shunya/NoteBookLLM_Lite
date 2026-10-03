import re


MAX_CHUNK_SIZE = 1000


def split_into_sentences(text: str) -> list[str]:
    """
    Split text into sentences while keeping the sentence content intact.
    """

    # Normalize whitespace.
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    # Basic sentence boundary detection.
    sentences = re.split(r"(?<=[.!?])\s+", text)

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]


def create_chunks(
    text: str,
    page_number: int,
    document_id: str
) -> list[dict]:
    """
    Convert page text into retrieval-friendly chunks.

    Chunks do not intentionally overlap.
    Sentences are kept intact whenever possible.
    """

    sentences = split_into_sentences(text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:

        # If adding this sentence stays within our target size,
        # keep building the current chunk.
        if (
            len(current_chunk) + len(sentence) + 1
            <= MAX_CHUNK_SIZE
        ):
            current_chunk = (
                f"{current_chunk} {sentence}"
                if current_chunk
                else sentence
            )

        else:
            # Save the current chunk before starting another one.
            if current_chunk:
                chunks.append({
                    "chunk_id": len(chunks) + 1,
                    "document_id": document_id,
                    "page_number": page_number,
                    "text": current_chunk
                })

            current_chunk = sentence

    # Don't forget the final chunk.
    if current_chunk:
        chunks.append({
            "chunk_id": len(chunks) + 1,
            "document_id": document_id,
            "page_number": page_number,
            "text": current_chunk
        })

    return chunks