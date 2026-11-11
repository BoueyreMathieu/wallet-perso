"""Heure d'enregistrement des soldes (pour le solde calculé avec les saisies manuelles)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("balance_snapshot") as batch:
        batch.add_column(sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade() -> None:
    with op.batch_alter_table("balance_snapshot") as batch:
        batch.drop_column("recorded_at")
