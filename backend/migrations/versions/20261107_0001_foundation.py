"""Create accounts and model catalog."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261107_0001"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("email_normalized", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        *timestamps(),
        sa.UniqueConstraint("email_normalized"),
    )
    op.create_table(
        "credit_accounts",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("available", sa.Numeric(20, 4), server_default="0.0000", nullable=False),
        sa.Column("frozen", sa.Numeric(20, 4), server_default="0.0000", nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "available >= 0 AND available < 'Infinity'::numeric",
            name=op.f("ck_credit_accounts_available"),
        ),
        sa.CheckConstraint(
            "frozen >= 0 AND frozen < 'Infinity'::numeric",
            name=op.f("ck_credit_accounts_frozen"),
        ),
    )
    op.create_table(
        "providers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("adapter_key", sa.String(80), nullable=False),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("request_config", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        *timestamps(),
    )
    op.create_table(
        "models",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("provider_id", sa.BigInteger(), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("upstream_model_id", sa.String(160), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("pricing_dimensions", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        *timestamps(),
        sa.UniqueConstraint("public_id"),
        sa.CheckConstraint("media_type IN ('image', 'video')", name=op.f("ck_models_media_type")),
        sa.CheckConstraint(
            "jsonb_typeof(capabilities) = 'object'", name=op.f("ck_models_capabilities")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(pricing_dimensions) = 'array'", name=op.f("ck_models_pricing_dimensions")
        ),
    )
    op.create_table(
        "model_prices",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("model_id", sa.BigInteger(), sa.ForeignKey("models.id"), nullable=False),
        sa.Column("variant", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("sale_unit", sa.String(16), nullable=False),
        sa.Column("sale_unit_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("cost_unit", sa.String(32), nullable=False),
        sa.Column("cost_unit_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("cost_currency", sa.String(16), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("model_id", "variant"),
        sa.CheckConstraint(
            "jsonb_typeof(variant) = 'object'", name=op.f("ck_model_prices_variant")
        ),
        sa.CheckConstraint(
            "sale_unit IN ('image', 'video', 'second')", name=op.f("ck_model_prices_sale_unit")
        ),
        sa.CheckConstraint(
            "sale_unit_price >= 0 AND sale_unit_price < 'Infinity'::numeric",
            name=op.f("ck_model_prices_sale_price"),
        ),
        sa.CheckConstraint(
            "cost_unit_price >= 0 AND cost_unit_price < 'Infinity'::numeric",
            name=op.f("ck_model_prices_cost_price"),
        ),
    )


def downgrade() -> None:
    for table in ("model_prices", "models", "providers", "credit_accounts", "users"):
        op.drop_table(table)
