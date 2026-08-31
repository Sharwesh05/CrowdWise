"""widen ai_community_insights.risk_change to Text

A real LLM writes a two-clause verdict here and overruns String(200) routinely,
which surfaced as StringDataRightTruncation on insert. The Pydantic validator
already allowed 1500 chars, and the sibling column community_summary is Text —
this aligns the column with both.

Revision ID: a1c4e7b90d21
Revises: 04b51c348061
Create Date: 2026-08-30

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1c4e7b90d21"
down_revision = "04b51c348061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_community_insights") as batch:
        batch.alter_column(
            "risk_change",
            existing_type=sa.String(length=200),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Values longer than 200 chars cannot survive the narrowing; truncate first.
    op.execute(
        "UPDATE ai_community_insights SET risk_change = left(risk_change, 200) "
        "WHERE risk_change IS NOT NULL"
    )
    with op.batch_alter_table("ai_community_insights") as batch:
        batch.alter_column(
            "risk_change",
            existing_type=sa.Text(),
            type_=sa.String(length=200),
            existing_nullable=True,
        )
