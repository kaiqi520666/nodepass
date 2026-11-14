"""Eight decimal credits and Gemini token billing."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261111_0011"
down_revision = "20261109_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, columns in (
        ("credit_accounts", ("available", "frozen")),
        ("credit_entries", ("amount", "available_delta", "frozen_delta")),
        ("tasks", ("frozen_amount",)),
        ("model_prices", ("sale_unit_price",)),
    ):
        for column in columns:
            op.alter_column(table, column, type_=sa.Numeric(24, 8))
    for column in ("available", "frozen"):
        op.alter_column("credit_accounts", column, server_default="0.00000000")
    op.drop_constraint(op.f("ck_credit_accounts_available"), "credit_accounts", type_="check")
    op.create_check_constraint(
        "available",
        "credit_accounts",
        "available > '-Infinity'::numeric AND available < 'Infinity'::numeric",
    )
    op.drop_constraint(op.f("ck_models_media_type"), "models", type_="check")
    op.create_check_constraint("media_type", "models", "media_type IN ('image', 'video', 'text')")
    op.drop_constraint(op.f("ck_credit_entries_entry_type"), "credit_entries", type_="check")
    op.create_check_constraint(
        "entry_type",
        "credit_entries",
        "entry_type IN ('freeze', 'settle', 'release', 'refund', 'recharge', "
        "'admin_credit', 'admin_debit', 'text_charge')",
    )
    price_fields = (
        "input_price",
        "output_price",
        "cache_read_price",
        "cost_multiplier",
        "sale_multiplier",
    )

    def timestamps():
        return [
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        ]

    op.create_table(
        "token_prices",
        sa.Column("model_id", sa.BigInteger(), sa.ForeignKey("models.id"), primary_key=True),
        *[sa.Column(field, sa.Numeric(24, 8), nullable=False) for field in price_fields],
        *timestamps(),
        *[
            sa.CheckConstraint(f"{field} >= 0 AND {field} < 'Infinity'::numeric", name=field)
            for field in price_fields
        ],
    )
    op.create_table(
        "text_calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("model_id", sa.BigInteger(), sa.ForeignKey("models.id"), nullable=False),
        sa.Column("provider_id", sa.BigInteger(), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("endpoint", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("price_snapshot", JSONB, nullable=False),
        sa.Column("usage", JSONB, nullable=True),
        sa.Column("charge_amount", sa.Numeric(24, 8), nullable=True),
        sa.Column("cost_amount", sa.Numeric(24, 8), nullable=True),
        sa.Column("error_message", sa.String(240), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('processing', 'succeeded', 'failed', 'usage_unknown')", name="status"
        ),
    )
    op.create_index("ix_text_calls_user_id", "text_calls", ["user_id"])


def downgrade() -> None:
    op.drop_table("text_calls")
    op.drop_table("token_prices")
    op.drop_constraint(op.f("ck_credit_entries_entry_type"), "credit_entries", type_="check")
    op.create_check_constraint(
        "entry_type",
        "credit_entries",
        "entry_type IN ('freeze', 'settle', 'release', 'refund', 'recharge', "
        "'admin_credit', 'admin_debit')",
    )
    op.drop_constraint(op.f("ck_models_media_type"), "models", type_="check")
    op.create_check_constraint("media_type", "models", "media_type IN ('image', 'video')")
    op.drop_constraint(op.f("ck_credit_accounts_available"), "credit_accounts", type_="check")
    op.create_check_constraint(
        "available", "credit_accounts", "available >= 0 AND available < 'Infinity'::numeric"
    )
    for table, columns in (
        ("credit_accounts", ("available", "frozen")),
        ("credit_entries", ("amount", "available_delta", "frozen_delta")),
        ("tasks", ("frozen_amount",)),
        ("model_prices", ("sale_unit_price",)),
    ):
        for column in columns:
            op.alter_column(table, column, type_=sa.Numeric(20, 4))
    for column in ("available", "frozen"):
        op.alter_column("credit_accounts", column, server_default="0.0000")
