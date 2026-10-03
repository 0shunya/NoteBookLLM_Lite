import uuid

from sqlalchemy.orm import Session

from app.db.models import ModelCall


def create_trace_id() -> str:
    """
    Create a unique identifier for one model-generation trace.
    """

    return str(uuid.uuid4())


def record_model_call(
    db: Session,
    *,
    trace_id: str,
    build: str,
    feature: str,
    attempt_number: int,
    provider: str,
    model: str,
    prompt_version: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_usd: float | None,
    latency_ms: int | None,
    status: str,
) -> ModelCall:
    """
    Persist metadata about one model call.

    Each actual model invocation gets its own record.

    IMPORTANT:
        This function intentionally does not accept or store API keys.
    """

    model_call = ModelCall(
        trace_id=trace_id,
        build=build,
        feature=feature,
        attempt_number=attempt_number,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        status=status,
    )

    db.add(model_call)
    db.commit()
    db.refresh(model_call)

    return model_call