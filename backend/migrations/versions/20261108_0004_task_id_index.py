"""Use the unique task id index as the task id constraint."""

from alembic import op

revision = "20261108_0004"
down_revision = "20261108_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_tasks_task_id", "tasks", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("uq_tasks_task_id", "tasks", ["task_id"])
