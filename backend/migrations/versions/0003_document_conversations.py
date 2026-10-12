"""Scope conversations to one document and preserve existing chat history.

Revision ID: 0003_document_conversations
Revises: 0002_notebooks_ingestion
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_document_conversations"
down_revision = "0002_notebooks_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("document_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_conversations_document_id_documents",
        "conversations",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_conversations_document_id", "conversations", ["document_id"])

    # Older chats used every document in their notebook. Attach each existing
    # chat to its most recently cited document; chats without citations fall
    # back to an explicitly attached document, then the notebook's first PDF.
    op.execute(
        sa.text(
            """UPDATE conversations AS conversation
               SET document_id = COALESCE(
                   (
                       SELECT chunk.document_id
                       FROM messages AS message
                       JOIN citations AS citation ON citation.message_id = message.id
                       JOIN chunks AS chunk ON chunk.id = citation.chunk_id
                       WHERE message.conversation_id = conversation.id
                       ORDER BY message.created_at DESC, message.id DESC, citation.marker
                       LIMIT 1
                   ),
                   (
                       SELECT link.document_id
                       FROM conversation_documents AS link
                       WHERE link.conversation_id = conversation.id
                       ORDER BY link.document_id
                       LIMIT 1
                   ),
                   (
                       SELECT document.id
                       FROM documents AS document
                       WHERE document.notebook_id = conversation.notebook_id
                       ORDER BY document.created_at, document.id
                       LIMIT 1
                   )
               )
               WHERE conversation.document_id IS NULL"""
        )
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_document_id", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_document_id_documents", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "document_id")
