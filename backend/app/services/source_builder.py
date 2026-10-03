from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    """
    Represents a retrieved source chunk that can be provided
    to the generation model.

    A source may come from:
    - vector search
    - keyword search
    - both

    Therefore, distance can be None when the source was not
    retrieved by vector search.
    """

    source_id: int
    chunk_id: int
    document_id: str
    filename: str
    page_number: int
    text: str
    distance: float | None

    def to_prompt_text(self) -> str:
        """
        Convert the source into the format given to the LLM.
        """

        return (
            f"[{self.source_id}] "
            f"{self.filename} — p.{self.page_number}\n"
            f"{self.text}"
        )


def build_sources(search_results: list[dict]) -> list[Source]:
    """
    Convert retrieval results into Source objects.

    The retrieval layer may return:
    - distance for vector results
    - None for keyword-only results
    """

    sources = []

    for source_id, result in enumerate(search_results, start=1):
        sources.append(
            Source(
                source_id=source_id,
                chunk_id=result["chunk_id"],
                document_id=result["document_id"],
                filename=result.get("filename", "Unknown document"),
                page_number=result["page_number"],
                text=result["text"],
                distance=result.get("distance"),
            )
        )

    return sources


def build_source_prompt(sources: list[Source]) -> str:
    """
    Build the source block that will be sent to the generation model.
    """

    return "\n\n".join(
        source.to_prompt_text()
        for source in sources
    )