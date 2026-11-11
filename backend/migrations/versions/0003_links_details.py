"""Rapprochements entre comptes : counted, linked_id, details, status sur transaction

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transaction") as batch:
        batch.add_column(sa.Column("counted", sa.Boolean, nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("linked_id", sa.Integer, nullable=True))
        batch.add_column(sa.Column("details", sa.JSON, nullable=True))
        batch.add_column(sa.Column("status", sa.String(20), nullable=True))
        batch.create_foreign_key("fk_transaction_linked", "transaction", ["linked_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("transaction") as batch:
        batch.drop_constraint("fk_transaction_linked", type_="foreignkey")
        batch.drop_column("status")
        batch.drop_column("details")
        batch.drop_column("linked_id")
        batch.drop_column("counted")
