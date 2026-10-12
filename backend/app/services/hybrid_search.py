"""Reciprocal-rank fusion and a lightweight, inspectable reranking stage."""

from sqlalchemy.orm import Session

from app.services.keyword_search import STOPWORDS, search_keyword_chunks
from app.services.model_call_service import create_trace_id
from app.services.vector_search import search_similar_chunks


RRF_K = 60
RRF_WEIGHT = 0.8
OVERLAP_WEIGHT = 0.2


def reciprocal_rank(rank: int, k: int = RRF_K) -> float:
    if rank < 1:
        raise ValueError("Ranks are one-based and must be positive.")
    return 1.0 / (k + rank)


def fuse_ranked_results(
    vector_results: list[dict],
    keyword_results: list[dict],
    k: int = RRF_K,
) -> list[dict]:
    """Merge ranked candidate lists by chunk id using standard RRF."""
    chunks: dict[int, dict] = {}
    for source_results, rank_key in (
        (vector_results, "vector_rank"),
        (keyword_results, "keyword_rank"),
    ):
        for rank, result in enumerate(source_results, start=1):
            chunk_id = result["chunk_id"]
            if chunk_id not in chunks:
                chunks[chunk_id] = {
                    **result,
                    "vector_rank": None,
                    "keyword_rank": None,
                    "rrf_score": 0.0,
                }
            else:
                # Prefer vector fields when available, but retain all source
                # metadata from either retriever.
                existing = chunks[chunk_id]
                for key, value in result.items():
                    if value is not None:
                        existing[key] = value
            chunks[chunk_id][rank_key] = rank
            chunks[chunk_id]["rrf_score"] += reciprocal_rank(rank, k)

    return sorted(
        chunks.values(),
        key=lambda item: (-item["rrf_score"], item["chunk_id"]),
    )


def _terms(text: str) -> set[str]:
    import re

    return {
        term
        for term in re.findall(r"[a-zA-Z0-9]+", text.lower())
        if len(term) > 1 and term not in STOPWORDS
    }


def rerank_candidates(query: str, candidates: list[dict]) -> list[dict]:
    """Blend fused rank with query-term coverage for transparent reranking.

    This lexical reranker is deliberately small and deterministic. It can
    promote chunks that match more of the query's content terms without
    relying on another paid or downloaded model.
    """
    if not candidates:
        return []
    query_terms = _terms(query)
    best_rrf = max(float(item.get("rrf_score") or 0.0) for item in candidates) or 1.0

    ranked = []
    for item in candidates:
        text_terms = _terms(item.get("text", ""))
        coverage = len(query_terms & text_terms) / len(query_terms) if query_terms else 0.0
        fused = float(item.get("rrf_score") or 0.0) / best_rrf
        rerank_score = RRF_WEIGHT * fused + OVERLAP_WEIGHT * coverage
        ranked.append({
            **item,
            "query_term_coverage": coverage,
            "rerank_score": rerank_score,
        })

    return sorted(
        ranked,
        key=lambda item: (-item["rerank_score"], -item["rrf_score"], item["chunk_id"]),
    )


def rank_hybrid_candidates(
    query: str,
    vector_results: list[dict],
    keyword_results: list[dict],
    limit: int,
    k: int = RRF_K,
) -> list[dict]:
    fused = fuse_ranked_results(vector_results, keyword_results, k=k)
    return rerank_candidates(query, fused)[:limit]


def hybrid_search_chunks(
    db: Session,
    query: str,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
    limit: int = 5,
    candidate_limit: int = 20,
    trace_id: str | None = None,
) -> list[dict]:
    if not query.strip():
        raise ValueError("Search query cannot be empty.")
    if limit <= 0 or candidate_limit < limit:
        raise ValueError("candidate_limit must be at least the positive result limit.")
    if document_id is not None and document_ids is not None:
        raise ValueError("Provide either document_id or document_ids, not both.")
    if document_ids is not None and not document_ids:
        raise ValueError("document_ids cannot be empty.")

    vector_results = search_similar_chunks(
        db=db,
        query=query,
        document_id=document_id,
        document_ids=document_ids,
        limit=candidate_limit,
        trace_id=trace_id or create_trace_id(),
    )
    keyword_results = search_keyword_chunks(
        db=db,
        query=query,
        document_id=document_id,
        document_ids=document_ids,
        limit=candidate_limit,
    )
    return rank_hybrid_candidates(
        query=query,
        vector_results=vector_results,
        keyword_results=keyword_results,
        limit=limit,
    )
