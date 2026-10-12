"""Idempotent batch indexing for document chunks."""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Chunk, Embedding
from app.services.embedding_service import EMBEDDING_MODEL, generate_embedding_batch
from app.services.model_call_service import create_trace_id, record_model_call


BATCH_SIZE = 32


def embed_document_chunks(db: Session, document_id: str) -> int:
    chunks = db.scalars(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.id)
    ).all()
    if not chunks:
        return 0

    existing_ids = set(
        db.scalars(
            select(Embedding.chunk_id).where(
                Embedding.chunk_id.in_([chunk.id for chunk in chunks]),
                Embedding.model == EMBEDDING_MODEL,
            )
        ).all()
    )
    missing = [chunk for chunk in chunks if chunk.id not in existing_ids]
    embedded_count = 0

    for offset in range(0, len(missing), BATCH_SIZE):
        batch = missing[offset : offset + BATCH_SIZE]
        trace_id = create_trace_id()
        started = time.perf_counter()
        try:
            embedding_result = generate_embedding_batch([chunk.text for chunk in batch])
        except Exception as exc:
            record_model_call(
                db,
                trace_id=trace_id,
                build="notebooklm-lite",
                feature="document_embedding",
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
            trace_id=trace_id,
            build="notebooklm-lite",
            feature="document_embedding",
            attempt_number=1,
            provider="ollama",
            model=EMBEDDING_MODEL,
            prompt_version="embedding-v1",
            input_tokens=embedding_result.input_tokens,
            output_tokens=None,
            cost_usd=0.0,
            latency_ms=embedding_result.latency_ms,
            status="success",
            validation_result={
                "vector_count": len(embedding_result.vectors),
                "dimensions": settings.embedding_dimensions,
            },
            error_message=None,
        )
        db.add_all(
            Embedding(chunk_id=chunk.id, model=EMBEDDING_MODEL, embedding=vector)
            for chunk, vector in zip(batch, embedding_result.vectors, strict=True)
        )
        db.flush()
        embedded_count += len(batch)

    db.commit()
    return embedded_count
