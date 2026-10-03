from sqlalchemy.orm import Session

from app.services.keyword_search import search_keyword_chunks
from app.services.vector_search import search_similar_chunks


# Controls how strongly rank differences affect the RRF score.
RRF_K = 60


def reciprocal_rank(rank: int) -> float:
    """
    Calculate the Reciprocal Rank Fusion contribution
    for one result.

    Example:

        rank 1 → 1 / 61
        rank 2 → 1 / 62
        rank 3 → 1 / 63
    """

    return 1 / (RRF_K + rank)


def hybrid_search_chunks(
    db: Session,
    query: str,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
    limit: int = 3,
    candidate_limit: int = 10,
) -> list[dict]:
    """
    Perform hybrid retrieval using:

        Vector Search
             +
        Keyword Search
             ↓
            RRF
             ↓
        Combined ranking

    Retrieval can be restricted to:
    - one document using document_id
    - multiple documents using document_ids

    If neither is provided, all documents can be searched.
    """

    # -----------------------------------------------------------------------
    # Validate input
    # -----------------------------------------------------------------------

    if not query.strip():
        raise ValueError(
            "Search query cannot be empty."
        )

    if limit <= 0:
        raise ValueError(
            "Search limit must be greater than zero."
        )

    if candidate_limit < limit:
        raise ValueError(
            "candidate_limit must be greater than or equal to limit."
        )

    if document_id is not None and document_ids is not None:
        raise ValueError(
            "Provide either document_id or document_ids, not both."
        )

    if document_ids is not None and not document_ids:
        raise ValueError(
            "document_ids cannot be empty."
        )

    # -----------------------------------------------------------------------
    # Vector search
    # -----------------------------------------------------------------------

    vector_results = search_similar_chunks(
        db=db,
        query=query,
        document_id=document_id,
        document_ids=document_ids,
        limit=candidate_limit,
    )

    # -----------------------------------------------------------------------
    # Keyword search
    # -----------------------------------------------------------------------

    keyword_results = search_keyword_chunks(
        db=db,
        query=query,
        document_id=document_id,
        document_ids=document_ids,
        limit=candidate_limit,
    )

    # -----------------------------------------------------------------------
    # Combine results by chunk ID
    # -----------------------------------------------------------------------

    chunks: dict[int, dict] = {}

    # Add vector-search results.
    for result in vector_results:
        chunk_id = result["chunk_id"]

        chunks[chunk_id] = {
            **result,
            "vector_rank": None,
            "keyword_rank": None,
            "rrf_score": 0.0,
        }

    # Add keyword-only results.
    for result in keyword_results:
        chunk_id = result["chunk_id"]

        if chunk_id not in chunks:
            chunks[chunk_id] = {
                **result,
                "vector_rank": None,
                "keyword_rank": None,

                # Keyword-only result has no vector distance.
                "distance": None,

                # Keyword search doesn't have an embedding model.
                "model": None,

                "rrf_score": 0.0,
            }

    # -----------------------------------------------------------------------
    # Add vector RRF scores
    # -----------------------------------------------------------------------

    for rank, result in enumerate(
        vector_results,
        start=1,
    ):
        chunk_id = result["chunk_id"]

        chunks[chunk_id]["vector_rank"] = rank

        chunks[chunk_id]["rrf_score"] += reciprocal_rank(rank)

    # -----------------------------------------------------------------------
    # Add keyword RRF scores
    # -----------------------------------------------------------------------

    for rank, result in enumerate(
        keyword_results,
        start=1,
    ):
        chunk_id = result["chunk_id"]

        chunks[chunk_id]["keyword_rank"] = rank

        chunks[chunk_id]["rrf_score"] += reciprocal_rank(rank)

    # -----------------------------------------------------------------------
    # Sort by combined RRF score
    # -----------------------------------------------------------------------

    ranked_chunks = sorted(
        chunks.values(),
        key=lambda result: result["rrf_score"],
        reverse=True,
    )

    # -----------------------------------------------------------------------
    # Return top results
    # -----------------------------------------------------------------------

    return ranked_chunks[:limit]