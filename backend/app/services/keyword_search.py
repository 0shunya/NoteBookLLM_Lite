import re

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "which",
    "who",
    "with",
}


def extract_search_terms(query: str) -> list[str]:
    """
    Extract meaningful words from a natural-language query.

    Stopwords are removed because they usually add little
    retrieval value.
    """

    words = re.findall(
        r"[a-zA-Z0-9]+",
        query.lower(),
    )

    terms = []

    for word in words:
        if word in STOPWORDS:
            continue

        if len(word) < 2:
            continue

        if word not in terms:
            terms.append(word)

    return terms


def search_keyword_chunks(
    db: Session,
    query: str,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Find chunks using PostgreSQL full-text keyword search.

    Retrieval can optionally be restricted to:
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

    if document_id is not None and document_ids is not None:
        raise ValueError(
            "Provide either document_id or document_ids, not both."
        )

    if document_ids is not None and not document_ids:
        raise ValueError(
            "document_ids cannot be empty."
        )

    # -----------------------------------------------------------------------
    # Extract meaningful search terms
    # -----------------------------------------------------------------------

    terms = extract_search_terms(query)

    if not terms:
        return []

    # PostgreSQL OR query:
    #
    # Python OR PostgreSQL OR Docker
    #
    # Using OR makes natural-language questions much more
    # tolerant than requiring every term to match.
    tsquery_text = " | ".join(terms)

    english_config = literal_column("'english'")
    search_query = func.to_tsquery(
        english_config,
        tsquery_text,
    )

    search_vector = func.to_tsvector(
        english_config,
        Chunk.text,
    )

    rank = func.ts_rank_cd(
        search_vector,
        search_query,
    )

    # -----------------------------------------------------------------------
    # Build base query
    # -----------------------------------------------------------------------

    statement = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.page_number,
            Chunk.page_start,
            Chunk.page_end,
            Chunk.text,
            Document.filename,
            rank.label("rank"),
        )
        .join(
            Document,
            Document.id == Chunk.document_id,
        )
        .where(
            search_vector.op("@@")(search_query)
        )
    )

    # -----------------------------------------------------------------------
    # Restrict retrieval to requested documents
    # -----------------------------------------------------------------------

    if document_id is not None:
        statement = statement.where(
            Chunk.document_id == document_id
        )

    elif document_ids is not None:
        statement = statement.where(
            Chunk.document_id.in_(document_ids)
        )

    # -----------------------------------------------------------------------
    # Execute keyword search
    # -----------------------------------------------------------------------

    statement = (
        statement
        .order_by(rank.desc())
        .limit(limit)
    )

    results = db.execute(statement).all()

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
            "rank": float(row.rank),
        }
        for row in results
    ]
