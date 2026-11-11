"""Table app_meta + suppression de la catégorie « Non catégorisé »

Une opération sans catégorie a désormais simplement category_id = NULL.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_meta",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )
    op.execute(
        "DELETE FROM category WHERE name = 'Non catégorisé' AND parent_id IS NULL "
        "AND id NOT IN (SELECT category_id FROM \"transaction\" WHERE category_id IS NOT NULL)"
    )


def downgrade() -> None:
    op.drop_table("app_meta")
