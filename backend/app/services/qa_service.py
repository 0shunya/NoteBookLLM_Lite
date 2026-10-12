"""Shared retrieval and grounded-generation flow for direct and chat QA."""

import re

from sqlalchemy.orm import Session

from app.config import settings
from app.services.generation_service import generate_answer
from app.services.hybrid_search import hybrid_search_chunks
from app.services.model_call_service import create_trace_id, record_generation_attempts
from app.services.source_builder import Source, build_sources


def build_retrieval_query(question: str, history: list[dict] | None) -> str:
    """Add recent user questions to short follow-ups before retrieval."""
    if not history:
        return question
    referential_terms = {
        "it", "they", "them", "those", "that", "these", "one", "ones",
        "second", "first", "same", "last",
    }
    has_reference = bool(referential_terms & set(re.findall(r"[a-z]+", question.lower())))
    if len(question.split()) >= 8 and not has_reference:
        return question
    recent_user_questions = [
        str(item.get("content", "")).strip()
        for item in history[-8:]
        if item.get("role") == "user" and str(item.get("content", "")).strip()
    ][-3:]
    if not recent_user_questions:
        return question
    return "\n".join([*recent_user_questions, f"Follow-up question: {question}"])[-2400:]


def answer_from_documents(
    *,
    db: Session,
    question: str,
    document_ids: list[str],
    feature: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    retrieval_query = build_retrieval_query(question, conversation_history)
    trace_id = create_trace_id()
    search_results = hybrid_search_chunks(
        db=db,
        query=retrieval_query,
        document_ids=document_ids,
        limit=settings.retrieval_result_limit,
        candidate_limit=max(settings.retrieval_candidate_limit, settings.retrieval_result_limit),
        trace_id=trace_id,
    )
    sources = build_sources(search_results)

    if not sources:
        return {
            "answer": "I could not find relevant information in the selected documents.",
            "sources": [],
            "validation": {
                "valid": True,
                "cited_source_ids": [],
                "invalid_source_ids": [],
                "uncited_sentences": [],
                "malformed_citations": [],
            },
            "attempts": [],
            "status": "success",
            "trace_id": trace_id,
        }

    generation = generate_answer(
        question=question,
        sources=sources,
        conversation_history=conversation_history,
    )
    record_generation_attempts(
        db,
        trace_id=trace_id,
        build="notebooklm-lite",
        feature=feature,
        prompt_version=settings.prompt_version,
        attempts=generation["attempts"],
    )
    return {
        **generation,
        "sources": sources,
        "trace_id": trace_id,
    }


def source_response(source: Source) -> dict:
    return {
        "id": source.source_id,
        "chunk_id": source.chunk_id,
        "document_id": source.document_id,
        "filename": source.filename,
        "page_number": source.page_number,
        "page_start": source.page_start or source.page_number,
        "page_end": source.page_end or source.page_number,
        "text": source.text,
        "distance": source.distance,
        "rrf_score": source.rrf_score,
        "rerank_score": source.rerank_score,
    }
