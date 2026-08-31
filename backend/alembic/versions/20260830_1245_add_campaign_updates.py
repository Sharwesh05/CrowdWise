"""add campaign_updates

Creator-authored progress posts. Deliberately separate from `feedback`: that
table flows from the community to the creator and carries sentiment columns,
while an update flows the other way and is never classified.

Revision ID: b2d5f8c31e40
Revises: a1c4e7b90d21
Create Date: 2026-08-30

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import app.core.db  # noqa: F401  (registers the UTCDateTime column type)

revision = "b2d5f8c31e40"
down_revision = "a1c4e7b90d21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_updates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        # SET NULL rather than CASCADE: deleting a user must not silently erase
        # the campaign's published history.
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", app.core.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.core.db.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_updates_campaign_id", "campaign_updates", ["campaign_id"])
    op.create_index("ix_campaign_updates_author_id", "campaign_updates", ["author_id"])
    op.create_index("ix_campaign_updates_created_at", "campaign_updates", ["created_at"])
    op.create_index(
        "ix_campaign_updates_campaign_created",
        "campaign_updates",
        ["campaign_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_campaign_updates_campaign_created", table_name="campaign_updates")
    op.drop_index("ix_campaign_updates_created_at", table_name="campaign_updates")
    op.drop_index("ix_campaign_updates_author_id", table_name="campaign_updates")
    op.drop_index("ix_campaign_updates_campaign_id", table_name="campaign_updates")
    op.drop_table("campaign_updates")
