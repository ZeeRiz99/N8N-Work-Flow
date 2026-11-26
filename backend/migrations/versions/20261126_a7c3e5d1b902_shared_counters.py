"""shared counters: Gemini daily budget and rate limits in PostgreSQL (backlog #42, #43)

Revision ID: a7c3e5d1b902
Revises: f52ac9821bff
Create Date: 2026-11-26 06:40:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e5d1b902"
down_revision: Union[str, Sequence[str], None] = "f52ac9821bff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_counters",
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("period", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("scope", "period", "key"),
    )
    op.create_table(
        "rate_limit_hits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_limit_hits_key_at", "rate_limit_hits", ["key", "at"])
    op.create_index("ix_rate_limit_hits_at", "rate_limit_hits", ["at"])


def downgrade() -> None:
    op.drop_index("ix_rate_limit_hits_at", table_name="rate_limit_hits")
    op.drop_index("ix_rate_limit_hits_key_at", table_name="rate_limit_hits")
    op.drop_table("rate_limit_hits")
    op.drop_table("usage_counters")
