"""Récurrents (abonnements, prélèvements, salaires, virements programmés) : détection et suivi

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recurring_series") as batch:
        batch.add_column(sa.Column("account_id", sa.Integer(), sa.ForeignKey("account.id", ondelete="CASCADE", name="fk_recurring_account"), nullable=True))
        batch.add_column(sa.Column("source", sa.String(10), nullable=False, server_default="auto"))
        batch.add_column(sa.Column("is_transfer", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("first_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("last_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("occurrences", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("previous_amount_cents", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("price_changed_on", sa.Date(), nullable=True))
        batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    # Ancienne valeur par défaut « actif » : les séries détectées commencent « à confirmer ».
    op.execute("UPDATE recurring_series SET status = 'suggere' WHERE status IS NULL")
    op.create_index("ix_transaction_recurring", "transaction", ["recurring_id"])


def downgrade() -> None:
    op.drop_index("ix_transaction_recurring", table_name="transaction")
    with op.batch_alter_table("recurring_series") as batch:
        for col in ("created_at", "price_changed_on", "previous_amount_cents", "occurrences", "last_date", "first_date", "is_transfer", "source", "account_id"):
            batch.drop_column(col)
