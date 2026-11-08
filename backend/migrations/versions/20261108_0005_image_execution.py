"""Add image execution metadata and result assets."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261108_0005"
down_revision = "20261108_0004"
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
    op.add_column(
        "tasks",
        sa.Column("provider_snapshot", postgresql.JSONB(), server_default="{}", nullable=False),
    )
    op.add_column("tasks", sa.Column("upstream_status", sa.String(64)))
    op.add_column("tasks", sa.Column("next_run_at", sa.DateTime(timezone=True)))
    op.add_column("tasks", sa.Column("submitted_at", sa.DateTime(timezone=True)))
    op.add_column("tasks", sa.Column("upstream_completed_at", sa.DateTime(timezone=True)))
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "tasks", sa.Column("review_required", sa.Boolean(), server_default="false", nullable=False)
    )
    op.create_index("ix_tasks_status_next_run_at", "tasks", ["status", "next_run_at"])

    op.create_table(
        "assets",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("source_url_encrypted", sa.Text()),
        sa.Column("oss_region", sa.String(128)),
        sa.Column("oss_bucket", sa.String(128)),
        sa.Column("oss_object_key", sa.String(1024)),
        sa.Column("public_url", sa.String(2048)),
        sa.Column("content_type", sa.String(160)),
        sa.Column("byte_size", sa.BigInteger()),
        sa.Column("checksum", sa.String(128)),
        sa.Column("ready_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "source_kind IN ('upload', 'external', 'generated')",
            name=op.f("ck_assets_source_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'error')",
            name=op.f("ck_assets_status"),
        ),
    )
    op.create_index("ix_assets_user_id", "assets", ["user_id"])

    op.create_table(
        "task_assets",
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("tasks.id"), primary_key=True),
        sa.Column("role", sa.String(16), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.BigInteger(), sa.ForeignKey("assets.id"), nullable=False),
        sa.UniqueConstraint("task_id", "role", "position"),
        sa.UniqueConstraint("task_id", "role", "asset_id"),
        sa.CheckConstraint(
            "role IN ('reference', 'mask', 'result')",
            name=op.f("ck_task_assets_role"),
        ),
        sa.CheckConstraint(
            "position >= 0",
            name=op.f("ck_task_assets_position"),
        ),
    )
    op.create_index("ix_task_assets_asset_id", "task_assets", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_task_assets_asset_id", table_name="task_assets")
    op.drop_table("task_assets")
    op.drop_index("ix_assets_user_id", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_tasks_status_next_run_at", table_name="tasks")
    for column in (
        "review_required",
        "completed_at",
        "upstream_completed_at",
        "submitted_at",
        "next_run_at",
        "upstream_status",
        "provider_snapshot",
    ):
        op.drop_column("tasks", column)
