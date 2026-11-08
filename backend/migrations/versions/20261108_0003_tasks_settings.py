"""Add system settings, generation tasks, and credit ledger."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261108_0003"
down_revision = "20261107_0002"
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
        "system_settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("secret_encrypted", sa.Text()),
        *timestamps(),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("model_id", sa.BigInteger(), sa.ForeignKey("models.id"), nullable=False),
        sa.Column("provider_id", sa.BigInteger(), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("price_id", sa.BigInteger(), sa.ForeignKey("model_prices.id"), nullable=False),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("billing_status", sa.String(16), server_default="held", nullable=False),
        sa.Column("request_params", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("model_snapshot", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("upstream_task_id", sa.String(200)),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("frozen_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("cost_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("cost_currency", sa.String(16), nullable=False),
        sa.Column("timed_out_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        *timestamps(),
        sa.UniqueConstraint("task_id"),
        sa.CheckConstraint(
            "status IN ('queued', 'submitting', 'submission_unknown', 'pending', "
            "'processing', 'transferring', 'succeeded', 'failed')",
            name=op.f("ck_tasks_status"),
        ),
        sa.CheckConstraint(
            "billing_status IN ('held', 'settled', 'released', 'refunded')",
            name=op.f("ck_tasks_billing_status"),
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_tasks_quantity")),
        sa.CheckConstraint(
            "frozen_amount >= 0 AND frozen_amount < 'Infinity'::numeric",
            name=op.f("ck_tasks_frozen"),
        ),
    )
    op.create_index("ix_tasks_task_id", "tasks", ["task_id"], unique=True)
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_table(
        "credit_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("tasks.id")),
        sa.Column("entry_type", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("available_delta", sa.Numeric(20, 4), nullable=False),
        sa.Column("frozen_delta", sa.Numeric(20, 4), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("idempotency_key"),
        sa.CheckConstraint(
            "entry_type IN ('freeze', 'settle', 'release', 'refund', 'recharge')",
            name=op.f("ck_credit_entries_entry_type"),
        ),
    )
    op.create_index("ix_credit_entries_user_id", "credit_entries", ["user_id"])
    op.create_index("ix_credit_entries_task_id", "credit_entries", ["task_id"])


def downgrade() -> None:
    op.drop_table("credit_entries")
    op.drop_index("ix_tasks_task_id", table_name="tasks")
    op.drop_index("ix_tasks_user_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("system_settings")
