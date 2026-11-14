"""Remove cost currency fields."""

import sqlalchemy as sa
from alembic import op

revision = "20261109_0009"
down_revision = "20261108_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("model_prices", "cost_currency")
    op.drop_column("tasks", "cost_currency")
    op.execute("UPDATE tasks SET model_snapshot = model_snapshot - 'cost_currency'")


def downgrade() -> None:
    for table in ("model_prices", "tasks"):
        op.add_column(
            table, sa.Column("cost_currency", sa.String(16), nullable=False, server_default="CNY")
        )
        op.alter_column(table, "cost_currency", server_default=None)
