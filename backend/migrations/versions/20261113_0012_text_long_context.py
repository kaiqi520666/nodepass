"""Snapshot long-context token pricing."""

import sqlalchemy as sa
from alembic import op

revision = "20261113_0012"
down_revision = "20261111_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "token_prices",
        sa.Column("long_context_threshold", sa.Integer(), nullable=False, server_default="272000"),
    )
    for field in ("long_context_input_multiplier", "long_context_output_multiplier"):
        op.add_column(
            "token_prices", sa.Column(field, sa.Numeric(24, 8), nullable=False, server_default="1")
        )
        op.create_check_constraint(
            field, "token_prices", f"{field} >= 0 AND {field} < 'Infinity'::numeric"
        )
        op.alter_column("token_prices", field, server_default=None)
    op.alter_column("token_prices", "long_context_threshold", server_default=None)
    op.create_check_constraint(
        "long_context_threshold", "token_prices", "long_context_threshold > 0"
    )
    op.execute("""
        UPDATE text_calls SET price_snapshot = price_snapshot || jsonb_build_object(
            'long_context_threshold', 272000,
            'long_context_input_multiplier', '1.00000000',
            'long_context_output_multiplier', '1.00000000'
        )
    """)


def downgrade() -> None:
    for field in (
        "long_context_threshold",
        "long_context_input_multiplier",
        "long_context_output_multiplier",
    ):
        op.drop_constraint(op.f(f"ck_token_prices_{field}"), "token_prices", type_="check")
        op.drop_column("token_prices", field)
