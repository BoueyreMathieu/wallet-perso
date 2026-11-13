"""Sécurité : sessions du navigateur en base (révocables) et journal de sécurité

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # « app » = appli Android / widgets (jeton Bearer) ; « navigateur » = session web (cookie).
    with op.batch_alter_table("device_token") as batch:
        batch.add_column(sa.Column("kind", sa.String(12), nullable=False, server_default="app"))
    op.create_table(
        "security_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("detail", sa.String(200), nullable=True),
    )
    op.create_index("ix_security_event_kind_created", "security_event", ["kind", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_security_event_kind_created", table_name="security_event")
    op.drop_table("security_event")
    with op.batch_alter_table("device_token") as batch:
        batch.drop_column("kind")
