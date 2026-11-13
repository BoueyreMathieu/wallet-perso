"""Récurrents repérés par catégorie (salaire, loyer… aux libellés changeants)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recurring_series") as batch:
        batch.add_column(sa.Column("basis", sa.String(10), nullable=False, server_default="vendeur"))


def downgrade() -> None:
    with op.batch_alter_table("recurring_series") as batch:
        batch.drop_column("basis")
