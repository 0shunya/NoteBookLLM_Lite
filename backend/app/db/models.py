import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.database import Base


# ===========================================================================
# Conversation ↔ Document association table
# ===========================================================================

conversation_documents = Table(
    "conversation_documents",
    Base.metadata,
    Column(
        "conversation_id",
        String(36),
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    ),
    Column(
        "document_id",
        String(36),
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    ),
)


# ===========================================================================
# Document
# ===========================================================================

class Document(Base):
    """
    Represents one uploaded PDF.
    """

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    page_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        secondary=conversation_documents,
        back_populates="documents",
    )


# ===========================================================================
# Chunk
# ===========================================================================

class Chunk(Base):
    """
    Represents one retrieval unit extracted from a document.
    """

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    document: Mapped["Document"] = relationship(
        back_populates="chunks",
    )

    embedding: Mapped["Embedding | None"] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
        uselist=False,
    )


# ===========================================================================
# Embedding
# ===========================================================================

class Embedding(Base):
    """
    Stores the vector representation of a chunk.
    """

    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    chunk_id: Mapped[int] = mapped_column(
        ForeignKey(
            "chunks.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    embedding: Mapped[list[float]] = mapped_column(
        Vector(768),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    chunk: Mapped["Chunk"] = relationship(
        back_populates="embedding",
    )


# ===========================================================================
# Conversation
# ===========================================================================

class Conversation(Base):
    """
    Represents one chat session.

    A conversation can reference multiple documents.
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="New conversation",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    documents: Mapped[list["Document"]] = relationship(
        secondary=conversation_documents,
        back_populates="conversations",
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


# ===========================================================================
# Message
# ===========================================================================

class Message(Base):
    """
    Represents one message inside a conversation.

    role:
        user       → message written by the user
        assistant  → generated response
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
    )

# ===========================================================================
# Model Call
# ===========================================================================

# ===========================================================================
# Model Call
# ===========================================================================

class ModelCall(Base):
    """
    Records one call made to an LLM provider.

    This is an observability/audit record for AI model usage.

    IMPORTANT:
        API keys and other secrets must NEVER be stored here.
    """

    __tablename__ = "model_calls"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    trace_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    build: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    feature: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    prompt_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    input_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    output_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    cost_usd: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

# ===========================================================================
# Indexes
# ===========================================================================

Index(
    "ix_embeddings_embedding_hnsw",
    Embedding.embedding,
    postgresql_using="hnsw",
    postgresql_ops={
        "embedding": "vector_cosine_ops",
    },
)