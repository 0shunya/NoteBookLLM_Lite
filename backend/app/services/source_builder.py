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
    page_start: int | None = None
    page_end: int | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None

    def to_prompt_text(self) -> str:
        """
        Convert the source into the format given to the LLM.
        """

        start = self.page_start or self.page_number
        end = self.page_end or self.page_number
        page_label = f"p.{start}" if start == end else f"pp.{start}-{end}"
        return (
            f"[{self.source_id}] "
            f"{self.filename} — {page_label}\n"
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
                page_start=result.get("page_start", result["page_number"]),
                page_end=result.get("page_end", result["page_number"]),
                rrf_score=result.get("rrf_score"),
                rerank_score=result.get("rerank_score"),
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
