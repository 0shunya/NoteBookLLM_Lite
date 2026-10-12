"""Add notebooks, ingestion state, model-versioned vectors and citations.

Revision ID: 0002_notebooks_ingestion
Revises: 0001_legacy_schema
"""

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0002_notebooks_ingestion"
down_revision = "0001_legacy_schema"
branch_labels = None
depends_on = None


def _has_constraint(table: str, name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(item.get("name") == name for item in inspector.get_unique_constraints(table))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "notebooks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.add_column("documents", sa.Column("notebook_id", sa.String(36), nullable=True))
    op.add_column("documents", sa.Column("storage_key", sa.String(512), nullable=True))
    op.add_column("documents", sa.Column("sha256", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("status", sa.String(30), nullable=False, server_default="indexed"))
    op.add_column("documents", sa.Column("ingestion_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("ingestion_warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("documents", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("documents", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    # Keep documents from the original notebook-less app visible after upgrade.
    # Fresh installations have no documents yet, so they start without a seed notebook.
    bind = op.get_bind()
    has_legacy_documents = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM documents)")
    ).scalar()
    if has_legacy_documents:
        legacy_notebook_id = str(uuid.uuid4())
        bind.execute(
            sa.text("INSERT INTO notebooks (id, title) VALUES (:id, :title)"),
            {"id": legacy_notebook_id, "title": "Imported documents"},
        )
        bind.execute(
            sa.text("UPDATE documents SET notebook_id = :id WHERE notebook_id IS NULL"),
            {"id": legacy_notebook_id},
        )

    op.create_foreign_key(
        "fk_documents_notebook_id_notebooks",
        "documents",
        "notebooks",
        ["notebook_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_documents_notebook_id", "documents", ["notebook_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    if not _has_constraint("documents", "uq_documents_notebook_sha256"):
        op.create_unique_constraint(
            "uq_documents_notebook_sha256", "documents", ["notebook_id", "sha256"]
        )

    op.add_column("chunks", sa.Column("chunk_index", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("page_start", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("page_end", sa.Integer(), nullable=True))
    op.execute(
        """UPDATE chunks AS target
           SET chunk_index = source.row_number - 1,
               page_start = target.page_number,
               page_end = target.page_number
           FROM (
               SELECT id, ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY id) AS row_number
               FROM chunks
           ) AS source
           WHERE target.id = source.id"""
    )
    op.alter_column("chunks", "chunk_index", nullable=False, server_default="0")
    op.alter_column("chunks", "page_start", nullable=False, server_default="1")
    op.alter_column("chunks", "page_end", nullable=False, server_default="1")
    if not _has_constraint("chunks", "uq_chunks_document_index"):
        op.create_unique_constraint(
            "uq_chunks_document_index", "chunks", ["document_id", "chunk_index"]
        )
    op.create_index(
        "ix_chunks_text_fts",
        "chunks",
        [sa.text("to_tsvector('english', text)")],
        postgresql_using="gin",
    )

    op.add_column("conversations", sa.Column("notebook_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_conversations_notebook_id_notebooks",
        "conversations",
        "notebooks",
        ["notebook_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_conversations_notebook_id", "conversations", ["notebook_id"])

    op.add_column("messages", sa.Column("trace_id", sa.String(100), nullable=True))
    op.create_index("ix_messages_trace_id", "messages", ["trace_id"])

    # The original table allowed only one embedding per chunk. Model-specific
    # vectors need a composite uniqueness key so re-embedding is additive.
    uniques = sa.inspect(op.get_bind()).get_unique_constraints("embeddings")
    for item in uniques:
        if item.get("column_names") == ["chunk_id"] and item.get("name"):
            op.drop_constraint(item["name"], "embeddings", type_="unique")
    if not _has_constraint("embeddings", "uq_embeddings_chunk_model"):
        op.create_unique_constraint(
            "uq_embeddings_chunk_model", "embeddings", ["chunk_id", "model"]
        )

    op.add_column("model_calls", sa.Column("validation_result", sa.JSON(), nullable=True))
    op.add_column("model_calls", sa.Column("error_message", sa.Text(), nullable=True))
    op.create_index("ix_model_calls_created_at", "model_calls", ["created_at"])
    if not _has_constraint("model_calls", "uq_model_calls_trace_feature_attempt"):
        op.create_unique_constraint(
            "uq_model_calls_trace_feature_attempt",
            "model_calls",
            ["trace_id", "feature", "attempt_number"],
        )

    op.create_table(
        "citations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.Integer(), sa.ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("marker", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.UniqueConstraint("message_id", "marker", name="uq_citations_message_marker"),
    )
    op.create_index("ix_citations_message_id", "citations", ["message_id"])
    op.create_index("ix_citations_chunk_id", "citations", ["chunk_id"])


def downgrade() -> None:
    op.drop_index("ix_citations_chunk_id", table_name="citations")
    op.drop_index("ix_citations_message_id", table_name="citations")
    op.drop_table("citations")

    op.drop_constraint(
        "uq_model_calls_trace_feature_attempt", "model_calls", type_="unique"
    )
    op.drop_index("ix_model_calls_created_at", table_name="model_calls")
    op.drop_column("model_calls", "error_message")
    op.drop_column("model_calls", "validation_result")

    op.drop_constraint("uq_embeddings_chunk_model", "embeddings", type_="unique")
    op.create_unique_constraint("embeddings_chunk_id_key", "embeddings", ["chunk_id"])

    op.drop_index("ix_messages_trace_id", table_name="messages")
    op.drop_column("messages", "trace_id")
    op.drop_index("ix_conversations_notebook_id", table_name="conversations")
    op.drop_constraint("fk_conversations_notebook_id_notebooks", "conversations", type_="foreignkey")
    op.drop_column("conversations", "notebook_id")

    op.drop_index("ix_chunks_text_fts", table_name="chunks")
    op.drop_constraint("uq_chunks_document_index", "chunks", type_="unique")
    op.drop_column("chunks", "page_end")
    op.drop_column("chunks", "page_start")
    op.drop_column("chunks", "chunk_index")

    op.drop_constraint("uq_documents_notebook_sha256", "documents", type_="unique")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_notebook_id", table_name="documents")
    op.drop_constraint("fk_documents_notebook_id_notebooks", "documents", type_="foreignkey")
    op.drop_column("documents", "updated_at")
    op.drop_column("documents", "created_at")
    op.drop_column("documents", "ingestion_warnings")
    op.drop_column("documents", "ingestion_error")
    op.drop_column("documents", "status")
    op.drop_column("documents", "sha256")
    op.drop_column("documents", "storage_key")
    op.drop_column("documents", "notebook_id")
    op.drop_table("notebooks")
