"""Projets par étiquette, contrats (échéances, préavis) et réglages de patrimoine par compte

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tag.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("budget_cents", sa.BigInteger(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "contract",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(150), nullable=False),
        sa.Column("recurring_id", sa.Integer(), sa.ForeignKey("recurring_series.id", ondelete="SET NULL"), nullable=True),
        sa.Column("renewal_date", sa.Date(), nullable=False),
        sa.Column("notice_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("renew_months", sa.Integer(), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("account") as batch:
        batch.add_column(sa.Column("params", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("account") as batch:
        batch.drop_column("params")
    op.drop_table("contract")
    op.drop_table("project")
