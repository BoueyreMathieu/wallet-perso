"""Services par vendeur (règles enrichies) + étiquettes

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rule") as batch:
        batch.add_column(sa.Column("label", sa.String(100), nullable=True))
        batch.add_column(sa.Column("amount_min_cents", sa.BigInteger, nullable=True))
        batch.add_column(sa.Column("amount_max_cents", sa.BigInteger, nullable=True))
    with op.batch_alter_table("transaction") as batch:
        batch.add_column(sa.Column("rule_id", sa.Integer, nullable=True))
        batch.create_foreign_key("fk_transaction_rule", "rule", ["rule_id"], ["id"], ondelete="SET NULL")
    op.create_table(
        "tag",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("color", sa.String(7)),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "transaction_tag",
        sa.Column("transaction_id", sa.Integer, sa.ForeignKey("transaction.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "merchant_tag",
        sa.Column("merchant_id", sa.Integer, sa.ForeignKey("merchant.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "rule_tag",
        sa.Column("rule_id", sa.Integer, sa.ForeignKey("rule.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    for t in ("rule_tag", "merchant_tag", "transaction_tag", "tag"):
        op.drop_table(t)
    with op.batch_alter_table("transaction") as batch:
        batch.drop_constraint("fk_transaction_rule", type_="foreignkey")
        batch.drop_column("rule_id")
    with op.batch_alter_table("rule") as batch:
        batch.drop_column("amount_max_cents")
        batch.drop_column("amount_min_cents")
        batch.drop_column("label")
