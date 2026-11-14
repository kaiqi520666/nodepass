"""Support precise video billing quantities and supplier time snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261109_0010"
down_revision = "20261109_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("result_snapshot", JSONB, nullable=False, server_default="[]"))
    op.alter_column(
        "tasks", "quantity", type_=sa.Numeric(24, 8), postgresql_using="quantity::numeric"
    )
    op.execute(
        """UPDATE providers SET request_config =
        '{"timeout_seconds": 60,"poll_interval_seconds": 5,"task_timeout_seconds": 1800}'::jsonb
        || request_config"""
    )
    op.execute(
        """UPDATE tasks SET provider_snapshot = jsonb_set(
        provider_snapshot, '{request_config}',
        '{"timeout_seconds": 60,"poll_interval_seconds": 5,"task_timeout_seconds": 1800}'::jsonb
        || COALESCE(provider_snapshot->'request_config', '{}'::jsonb))"""
    )


def downgrade() -> None:
    op.drop_column("tasks", "result_snapshot")
    op.alter_column("tasks", "quantity", type_=sa.Integer(), postgresql_using="quantity::integer")
    op.execute("UPDATE providers SET request_config = request_config - 'task_timeout_seconds'")
    op.execute(
        """UPDATE tasks SET provider_snapshot =
        provider_snapshot #- '{request_config,task_timeout_seconds}'"""
    )
