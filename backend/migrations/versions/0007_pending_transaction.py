"""Opérations « à venir » (pas encore comptabilisées par la banque)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_transaction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("booked_at", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("raw_label", sa.String(500), nullable=False),
        sa.Column("merchant", sa.String(150), nullable=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("pending_transaction")
