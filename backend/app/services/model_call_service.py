"""Database persistence for model-attempt observability."""

import uuid

from sqlalchemy.orm import Session

from app.db.models import ModelCall
from app.services.generation_service import GenerationAttempt


def create_trace_id() -> str:
    return str(uuid.uuid4())


def record_generation_attempts(
    db: Session,
    *,
    trace_id: str,
    build: str,
    feature: str,
    prompt_version: str,
    attempts: list[GenerationAttempt],
) -> list[ModelCall]:
    records = [
        ModelCall(
            trace_id=trace_id,
            build=build,
            feature=feature,
            attempt_number=attempt.attempt_number,
            provider=attempt.provider,
            model=attempt.model,
            prompt_version=prompt_version,
            input_tokens=attempt.input_tokens,
            output_tokens=attempt.output_tokens,
            # Local inference has no provider invoice. Hosted provider pricing
            # is intentionally left unknown unless a pricing table is added.
            cost_usd=0.0 if attempt.provider == "ollama" else None,
            latency_ms=attempt.latency_ms,
            status=attempt.status,
            validation_result=attempt.validation,
            error_message=attempt.error,
        )
        for attempt in attempts
    ]
    if not records:
        return []
    db.add_all(records)
    db.commit()
    return records


def record_model_call(db: Session, **fields) -> ModelCall:
    """Compatibility helper for older local scripts."""
    record = ModelCall(**fields)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
