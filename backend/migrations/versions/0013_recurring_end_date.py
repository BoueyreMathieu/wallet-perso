"""Date de fin d'un récurrent (ex. paiement en 3 fois) et objectifs d'épargne datés

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recurring_series") as batch:
        batch.add_column(sa.Column("end_date", sa.Date(), nullable=True))
    with op.batch_alter_table("goal") as batch:
        batch.add_column(sa.Column("icon", sa.String(8), nullable=True))
        batch.add_column(sa.Column("saved_cents", sa.BigInteger(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("goal") as batch:
        batch.drop_column("priority")
        batch.drop_column("saved_cents")
        batch.drop_column("icon")
    with op.batch_alter_table("recurring_series") as batch:
        batch.drop_column("end_date")
