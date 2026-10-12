"""Small, page-preserving text chunker for parsed PDF pages."""

import re


MAX_CHUNK_SIZE = 1400
CHUNK_OVERLAP_CHARS = 140


def split_into_sentences(text: str) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip()
    ]


def _overlap_suffix(text: str) -> str:
    if len(text) <= CHUNK_OVERLAP_CHARS:
        return text
    suffix = text[-CHUNK_OVERLAP_CHARS:]
    return suffix[suffix.find(" ") + 1 :].strip() if " " in suffix else suffix


def create_chunks(
    text: str,
    page_number: int,
    document_id: str,
) -> list[dict]:
    """Pack paragraphs and sentences into overlapping, page-aware chunks."""
    normalized = re.sub(r"\r\n?", "\n", text or "")
    paragraphs = [re.sub(r"\s+", " ", value).strip() for value in re.split(r"\n\s*\n", normalized)]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]

    # PDF extractors often return one line per visual row. If no blank-line
    # separators exist, sentence boundaries still preserve readable units.
    sentences = [sentence for paragraph in paragraphs for sentence in split_into_sentences(paragraph)]
    chunks: list[dict] = []
    current = ""

    for sentence in sentences:
        if not current:
            current = sentence
            if len(current) <= MAX_CHUNK_SIZE:
                continue

            while len(current) > MAX_CHUNK_SIZE:
                split_at = current.rfind(" ", 0, MAX_CHUNK_SIZE)
                split_at = split_at if split_at > 0 else MAX_CHUNK_SIZE
                piece = current[:split_at].strip()
                chunks.append(
                    {
                        "chunk_id": len(chunks) + 1,
                        "document_id": document_id,
                        "page_number": page_number,
                        "page_start": page_number,
                        "page_end": page_number,
                        "text": piece,
                    }
                )
                current = f"{_overlap_suffix(piece)} {current[split_at:].strip()}".strip()
            continue

        if len(current) + len(sentence) + 1 <= MAX_CHUNK_SIZE:
            current = f"{current} {sentence}"
            continue

        chunks.append(
            {
                "chunk_id": len(chunks) + 1,
                "document_id": document_id,
                "page_number": page_number,
                "page_start": page_number,
                "page_end": page_number,
                "text": current.strip(),
            }
        )
        current = f"{_overlap_suffix(current)} {sentence}".strip()

        # An exceptionally long sentence is split only as a last resort.
        while len(current) > MAX_CHUNK_SIZE:
            split_at = current.rfind(" ", 0, MAX_CHUNK_SIZE)
            split_at = split_at if split_at > 0 else MAX_CHUNK_SIZE
            piece = current[:split_at].strip()
            chunks.append(
                {
                    "chunk_id": len(chunks) + 1,
                    "document_id": document_id,
                    "page_number": page_number,
                    "page_start": page_number,
                    "page_end": page_number,
                    "text": piece,
                }
            )
            current = f"{_overlap_suffix(piece)} {current[split_at:].strip()}".strip()

    if current:
        chunks.append(
            {
                "chunk_id": len(chunks) + 1,
                "document_id": document_id,
                "page_number": page_number,
                "page_start": page_number,
                "page_end": page_number,
                "text": current,
            }
        )

    return chunks
