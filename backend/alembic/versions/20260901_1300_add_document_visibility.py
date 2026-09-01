"""add visibility and extracted text to campaign_documents

Supporting documents gain a reader tier and a place to keep the text the AI
analyst reads. Existing rows become AI_ONLY: they were uploaded when the only
readers were the creator and an admin, so publishing them to every signed-in
user would widen an audience their uploader never agreed to.

Revision ID: c3e6a9d42f51
Revises: b2d5f8c31e40
Create Date: 2026-09-01

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import app.core.db  # noqa: F401  (registers the UTCDateTime column type)

revision = "c3e6a9d42f51"
down_revision = "b2d5f8c31e40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaign_documents",
        sa.Column(
            "visibility",
            sa.String(length=20),
            nullable=False,
            server_default="AI_ONLY",
        ),
    )
    op.add_column(
        "campaign_documents", sa.Column("extracted_text", sa.Text(), nullable=True)
    )
    op.add_column(
        "campaign_documents",
        sa.Column("extraction_note", sa.String(length=255), nullable=True),
    )
    # The server default exists only to backfill; the application always supplies
    # the value, and leaving it in place would hide a missing one.
    op.alter_column("campaign_documents", "visibility", server_default=None)


def downgrade() -> None:
    op.drop_column("campaign_documents", "extraction_note")
    op.drop_column("campaign_documents", "extracted_text")
    op.drop_column("campaign_documents", "visibility")
