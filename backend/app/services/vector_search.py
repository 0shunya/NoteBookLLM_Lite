from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document, Embedding
from app.services.embedding_service import generate_embedding


def search_similar_chunks(
    db: Session,
    query: str,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
    limit: int = 3,
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

    query_embedding = generate_embedding(query)

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
        query_statement
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
            "filename": row.filename,
            "text": row.text,
            "model": row.model,
            "distance": float(row.distance),
        }
        for row in results
    ]