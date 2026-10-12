"""Typed request and response contracts exposed by FastAPI."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NotebookCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class NotebookResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    document_count: int = 0


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="New conversation", max_length=255)
    notebook_id: str | None = None
    document_id: str


class ConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    document_id: str | None = None
    document_ids: list[str] | None = Field(default=None, max_length=100)
    notebook_id: str | None = None


class SourceResponse(BaseModel):
    id: int
    chunk_id: int
    document_id: str
    filename: str
    page_number: int
    page_start: int
    page_end: int
    text: str
    distance: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


class CitationValidationResponse(BaseModel):
    valid: bool
    cited_source_ids: list[int] = []
    invalid_source_ids: list[int] = []
    uncited_sentences: list[str] = []
    malformed_citations: list[str] = []


class AnswerResponse(BaseModel):
    question: str
    answer: str
    trace_id: str | None = None
    sources: list[SourceResponse] = []
    citation_validation: CitationValidationResponse
    generation_attempts: int
    status: Literal["success", "failure"]


class DocumentResponse(BaseModel):
    id: str
    document_id: str
    notebook_id: str | None = None
    filename: str
    page_count: int
    status: str
    ingestion_error: str | None = None
    ingestion_warnings: list[str] = []
    created_at: datetime
    updated_at: datetime


class CitationResponse(BaseModel):
    marker: int
    chunk_id: int | None
    document_id: str | None
    filename: str | None
    page_number: int
    quote: str


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    trace_id: str | None = None
    created_at: datetime
    citations: list[CitationResponse] = []


class ConversationResponse(BaseModel):
    conversation_id: str
    title: str
    notebook_id: str | None = None
    document_id: str | None = None
    created_at: datetime
    updated_at: datetime
    documents: list[dict] = []
    messages: list[MessageResponse] = []


class ModelCallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trace_id: str
    build: str
    feature: str
    provider: str
    model: str
    prompt_version: str
    attempt_number: int
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int | None
    status: str
    validation_result: dict | None = None
    error_message: str | None = None
    created_at: datetime


class PageResponse(BaseModel):
    document_id: str
    filename: str
    page_number: int
    page_count: int
    text: str


class HealthResponse(BaseModel):
    status: str
    database: str
    ollama: str
    model_provider: str
    model_ready: bool
    generation_model: str
    embedding_model: str


class NotebookAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
