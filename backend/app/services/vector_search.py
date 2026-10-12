import time

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document, Embedding
from app.services.embedding_service import EMBEDDING_MODEL, generate_embedding_batch
from app.services.model_call_service import create_trace_id, record_model_call


def search_similar_chunks(
    db: Session,
    query: str,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
    limit: int = 3,
    trace_id: str | None = None,
) -> list[dict]:
    """
    Find chunks that are semantically similar to a query.

    Retrieval can optionally be restricted to:
    - one document using document_id
    - multiple documents using document_ids

    If neither is provided, all documents can be searched.
    """

    # -----------------------------------------------------------------------
    # Validate input
    # -----------------------------------------------------------------------

    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    if limit <= 0:
        raise ValueError("Search limit must be greater than zero.")

    if document_id is not None and document_ids is not None:
        raise ValueError(
            "Provide either document_id or document_ids, not both."
        )

    if document_ids is not None and not document_ids:
        raise ValueError(
            "document_ids cannot be empty."
        )

    # -----------------------------------------------------------------------
    # Generate query embedding
    # -----------------------------------------------------------------------

    embedding_trace_id = trace_id or create_trace_id()
    started = time.perf_counter()
    try:
        embedding_result = generate_embedding_batch([query])
    except Exception as exc:
        record_model_call(
            db,
            trace_id=embedding_trace_id,
            build="notebooklm-lite",
            feature="query_embedding",
            attempt_number=1,
            provider="ollama",
            model=EMBEDDING_MODEL,
            prompt_version="embedding-v1",
            input_tokens=None,
            output_tokens=None,
            cost_usd=0.0,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status="failure",
            validation_result=None,
            error_message=f"{type(exc).__name__}: {exc}"[:500],
        )
        raise
    record_model_call(
        db,
        trace_id=embedding_trace_id,
        build="notebooklm-lite",
        feature="query_embedding",
        attempt_number=1,
        provider="ollama",
        model=EMBEDDING_MODEL,
        prompt_version="embedding-v1",
        input_tokens=embedding_result.input_tokens,
        output_tokens=None,
        cost_usd=0.0,
        latency_ms=embedding_result.latency_ms,
        status="success",
        validation_result={"vector_count": 1, "dimensions": len(embedding_result.vectors[0])},
        error_message=None,
    )
    query_embedding = embedding_result.vectors[0]

    distance = Embedding.embedding.cosine_distance(
        query_embedding
    )

    # -----------------------------------------------------------------------
    # Build base query
    # -----------------------------------------------------------------------

    query_statement = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.page_number,
            Chunk.page_start,
            Chunk.page_end,
            Chunk.text,
            Document.filename,
            Embedding.model,
            distance.label("distance"),
        )
        .join(
            Embedding,
            Embedding.chunk_id == Chunk.id,
        )
        .join(
            Document,
            Document.id == Chunk.document_id,
        )
        .where(Embedding.model == EMBEDDING_MODEL)
    )

    # -----------------------------------------------------------------------
    # Restrict retrieval to requested documents
    # -----------------------------------------------------------------------

    if document_id is not None:
        query_statement = query_statement.where(
            Chunk.document_id == document_id
        )

    elif document_ids is not None:
        query_statement = query_statement.where(
            Chunk.document_id.in_(document_ids)
        )

    # -----------------------------------------------------------------------
    # Execute vector search
    # -----------------------------------------------------------------------

    results = db.execute(
        _prepare_filtered_vector_scan(db, query_statement, document_id, document_ids)
        .order_by(distance)
        .limit(limit)
    ).all()

    # -----------------------------------------------------------------------
    # Normalize results
    # -----------------------------------------------------------------------

    return [
        {
            "chunk_id": row.id,
            "document_id": row.document_id,
            "page_number": row.page_number,
            "page_start": row.page_start,
            "page_end": row.page_end,
            "filename": row.filename,
            "text": row.text,
            "model": row.model,
            "distance": float(row.distance),
        }
        for row in results
    ]


def _prepare_filtered_vector_scan(
    db: Session,
    statement,
    document_id: str | None,
    document_ids: list[str] | None,
):
    """Enable pgvector iterative scans when a notebook filter is present.

    Older pgvector releases do not expose this setting; on those versions the
    indexed query still runs with the standard bounded HNSW scan.
    """
    if document_id is not None or document_ids is not None:
        try:
            db.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
        except DBAPIError:
            db.rollback()
    return statement
