"""Schéma initial

Revision ID: 0001
Revises:
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _tz() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "connection",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("consent_expires_at", _tz()),
        sa.Column("last_sync_at", _tz()),
        sa.Column("secrets_encrypted", sa.Text),
        sa.Column("created_at", _tz(), nullable=False),
    )
    op.create_table(
        "account",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("connection_id", sa.Integer, sa.ForeignKey("connection.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("institution", sa.String(100)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("external_id", sa.String(200)),
        sa.Column("include_in_net_worth", sa.Boolean, nullable=False),
        sa.Column("is_archived", sa.Boolean, nullable=False),
        sa.Column("created_at", _tz(), nullable=False),
        sa.UniqueConstraint("connection_id", "external_id", name="uq_account_external"),
    )
    op.create_table(
        "balance_snapshot",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("balance_cents", sa.BigInteger, nullable=False),
        sa.UniqueConstraint("account_id", "date", name="uq_balance_account_date"),
    )
    op.create_table(
        "import_batch",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("filename", sa.String(255)),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("account.id", ondelete="SET NULL")),
        sa.Column("started_at", _tz(), nullable=False),
        sa.Column("rows_total", sa.Integer, nullable=False),
        sa.Column("rows_imported", sa.Integer, nullable=False),
        sa.Column("rows_skipped", sa.Integer, nullable=False),
        sa.Column("errors", sa.JSON),
    )
    op.create_table(
        "category",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("category.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("color", sa.String(7)),
        sa.Column("icon", sa.String(50)),
        sa.UniqueConstraint("parent_id", "name", name="uq_category_parent_name"),
    )
    op.create_table(
        "merchant",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("aliases", sa.JSON),
        sa.Column("default_category_id", sa.Integer, sa.ForeignKey("category.id", ondelete="SET NULL")),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "recurring_series",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("label", sa.String(150), nullable=False),
        sa.Column("merchant_id", sa.Integer, sa.ForeignKey("merchant.id", ondelete="SET NULL")),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("category.id", ondelete="SET NULL")),
        sa.Column("expected_amount_cents", sa.BigInteger, nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("next_expected_date", sa.Date),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_table(
        "transaction",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("booked_at", sa.Date, nullable=False),
        sa.Column("value_date", sa.Date),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("raw_label", sa.Text, nullable=False),
        sa.Column("merchant_id", sa.Integer, sa.ForeignKey("merchant.id", ondelete="SET NULL")),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("category.id", ondelete="SET NULL")),
        sa.Column("is_transfer", sa.Boolean, nullable=False),
        sa.Column("transfer_pair_id", sa.Integer, sa.ForeignKey("transaction.id", ondelete="SET NULL")),
        sa.Column("recurring_id", sa.Integer, sa.ForeignKey("recurring_series.id", ondelete="SET NULL")),
        sa.Column("dedup_hash", sa.String(64), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("import_batch_id", sa.Integer, sa.ForeignKey("import_batch.id", ondelete="SET NULL")),
        sa.Column("note", sa.Text),
        sa.Column("category_locked", sa.Boolean, nullable=False),
        sa.Column("created_at", _tz(), nullable=False),
        sa.UniqueConstraint("account_id", "dedup_hash", name="uq_transaction_dedup"),
    )
    op.create_index("ix_transaction_account_date", "transaction", ["account_id", "booked_at"])
    op.create_index("ix_transaction_category", "transaction", ["category_id"])
    op.create_table(
        "rule",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pattern", sa.String(255), nullable=False),
        sa.Column("match_type", sa.String(20), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("category.id", ondelete="CASCADE")),
        sa.Column("merchant_id", sa.Integer, sa.ForeignKey("merchant.id", ondelete="CASCADE")),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column("from_correction", sa.Boolean, nullable=False),
        sa.Column("created_at", _tz(), nullable=False),
    )
    op.create_table(
        "budget",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("category.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monthly_amount_cents", sa.BigInteger, nullable=False),
        sa.Column("alert_threshold_pct", sa.Integer, nullable=False),
        sa.UniqueConstraint("category_id"),
    )
    op.create_table(
        "goal",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("target_cents", sa.BigInteger, nullable=False),
        sa.Column("target_date", sa.Date),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("account.id", ondelete="SET NULL")),
        sa.Column("created_at", _tz(), nullable=False),
    )
    op.create_table(
        "holding",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("avg_price", sa.Numeric(20, 6)),
        sa.Column("updated_at", _tz(), nullable=False),
        sa.UniqueConstraint("account_id", "isin", name="uq_holding_account_isin"),
    )
    op.create_table(
        "price_snapshot",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("price", sa.Numeric(20, 6), nullable=False),
        sa.UniqueConstraint("isin", "date", name="uq_price_isin_date"),
    )


def downgrade() -> None:
    for table in (
        "price_snapshot",
        "holding",
        "goal",
        "budget",
        "rule",
        "transaction",
        "recurring_series",
        "merchant",
        "category",
        "import_batch",
        "balance_snapshot",
        "account",
        "connection",
    ):
        op.drop_table(table)
