"""Give imported conversation history readable titles.

Revision ID: 0004_conversation_titles
Revises: 0003_document_conversations
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_conversation_titles"
down_revision = "0003_document_conversations"
branch_labels = None
depends_on = None


def _backfill_titles() -> None:
    op.execute(
        sa.text(
            """UPDATE conversations AS conversation
               SET title = CASE
                   WHEN LENGTH(BTRIM(first_message.content)) > 252
                       THEN LEFT(BTRIM(first_message.content), 252) || '…'
                   ELSE BTRIM(first_message.content)
               END
               FROM (
                   SELECT DISTINCT ON (conversation_id) conversation_id, content
                   FROM messages
                   WHERE role = 'user'
                   ORDER BY conversation_id, id
               ) AS first_message
               WHERE conversation.id = first_message.conversation_id
                 AND conversation.title = 'New conversation'
                 AND LENGTH(BTRIM(first_message.content)) > 0"""
        )
    )


def upgrade() -> None:
    _backfill_titles()


def downgrade() -> None:
    # Restore the generic title only when it still matches the first prompt.
    op.execute(
        sa.text(
            """UPDATE conversations AS conversation
               SET title = 'New conversation'
               FROM (
                   SELECT DISTINCT ON (conversation_id) conversation_id, content
                   FROM messages
                   WHERE role = 'user'
                   ORDER BY conversation_id, id
               ) AS first_message
               WHERE conversation.id = first_message.conversation_id
                 AND conversation.title = CASE
                     WHEN LENGTH(BTRIM(first_message.content)) > 252
                         THEN LEFT(BTRIM(first_message.content), 252) || '…'
                     ELSE BTRIM(first_message.content)
                 END"""
        )
    )
