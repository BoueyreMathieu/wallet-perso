"""Dernière erreur de synchro d'une connexion (affichée dans Connexions)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("connection") as batch:
        batch.add_column(sa.Column("last_error", sa.String(300), nullable=True))
        batch.add_column(sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("connection") as batch:
        batch.drop_column("last_error_at")
        batch.drop_column("last_error")
