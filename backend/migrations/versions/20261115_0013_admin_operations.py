"""Add admin operations and late text usage fields."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261115_0013"
down_revision = "20261113_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=True),
        sa.Column("credit_entry_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "before_snapshot",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "after_snapshot",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('task.requery', 'task.retry_transfer', 'task.release', "
            "'text.mark_unknown', 'text.manual_charge', 'text.close_no_charge', "
            "'user.credit_increase', 'user.credit_decrease')",
            name="action",
        ),
        sa.CheckConstraint(
            "target_type IN ('task', 'text_call', 'user')",
            name="target_type",
        ),
        sa.CheckConstraint(
            "amount IS NULL OR (amount >= 0 AND amount < 'Infinity'::numeric)",
            name="amount",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["credit_entry_id"], ["credit_entries.id"]),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(
        "ix_admin_actions_target",
        "admin_actions",
        ["target_type", "target_id", "created_at"],
    )
    op.create_index(
        "ix_admin_actions_actor",
        "admin_actions",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_admin_actions_action",
        "admin_actions",
        ["action", "created_at"],
    )
    op.execute("""
        CREATE FUNCTION prevent_admin_actions_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'admin_actions is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER admin_actions_immutable
        BEFORE UPDATE OR DELETE ON admin_actions
        FOR EACH ROW EXECUTE FUNCTION prevent_admin_actions_mutation()
    """)

    op.add_column("tasks", sa.Column("resolution", sa.String(32), nullable=True))
    op.add_column("tasks", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("resolved_by_user_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        None,
        "tasks",
        "users",
        ["resolved_by_user_id"],
        ["id"],
    )
    op.create_check_constraint(
        "resolution",
        "tasks",
        "resolution IS NULL OR resolution IN "
        "('manual_requeued', 'manual_retry_transfer', 'manual_released')",
    )
    op.create_index(
        "ix_tasks_review_required_status_created_at",
        "tasks",
        ["review_required", "status", "created_at"],
    )

    op.add_column("text_calls", sa.Column("resolution", sa.String(32), nullable=True))
    op.add_column("text_calls", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("text_calls", sa.Column("resolved_by_user_id", sa.BigInteger(), nullable=True))
    op.add_column("text_calls", sa.Column("late_usage", postgresql.JSONB(), nullable=True))
    op.add_column(
        "text_calls", sa.Column("late_usage_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        None,
        "text_calls",
        "users",
        ["resolved_by_user_id"],
        ["id"],
    )
    op.create_check_constraint(
        "resolution",
        "text_calls",
        "resolution IS NULL OR resolution IN "
        "('manual_marked_unknown', 'manual_charged', 'manual_closed_no_charge')",
    )
    op.drop_constraint(op.f("ck_text_calls_status"), "text_calls", type_="check")
    op.create_check_constraint(
        "status",
        "text_calls",
        "status IN ('processing', 'succeeded', 'failed', 'usage_unknown', "
        "'settled_manually', 'closed_no_charge')",
    )
    op.create_index("ix_text_calls_status_updated_at", "text_calls", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_text_calls_status_updated_at", table_name="text_calls")
    op.drop_constraint(op.f("ck_text_calls_status"), "text_calls", type_="check")
    op.create_check_constraint(
        "status",
        "text_calls",
        "status IN ('processing', 'succeeded', 'failed', 'usage_unknown')",
    )
    op.drop_constraint(op.f("ck_text_calls_resolution"), "text_calls", type_="check")
    op.drop_constraint(
        op.f("fk_text_calls_resolved_by_user_id_users"), "text_calls", type_="foreignkey"
    )
    op.drop_column("text_calls", "late_usage_at")
    op.drop_column("text_calls", "late_usage")
    op.drop_column("text_calls", "resolved_by_user_id")
    op.drop_column("text_calls", "resolved_at")
    op.drop_column("text_calls", "resolution")

    op.drop_index("ix_tasks_review_required_status_created_at", table_name="tasks")
    op.drop_constraint(op.f("ck_tasks_resolution"), "tasks", type_="check")
    op.drop_constraint(op.f("fk_tasks_resolved_by_user_id_users"), "tasks", type_="foreignkey")
    op.drop_column("tasks", "resolved_by_user_id")
    op.drop_column("tasks", "resolved_at")
    op.drop_column("tasks", "resolution")

    op.execute("DROP TRIGGER IF EXISTS admin_actions_immutable ON admin_actions")
    op.execute("DROP FUNCTION IF EXISTS prevent_admin_actions_mutation()")
    op.drop_table("admin_actions")
