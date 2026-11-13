"""Nature des catégories de dépenses (fixe / essentiel / plaisir) pour les prévisions par couche

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Vide = automatique (valeur par défaut de la catégorie, ou celle de sa catégorie principale).
    with op.batch_alter_table("category") as batch:
        batch.add_column(sa.Column("nature", sa.String(12), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("category") as batch:
        batch.drop_column("nature")
