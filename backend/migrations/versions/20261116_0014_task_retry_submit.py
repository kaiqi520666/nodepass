"""Allow audited recovery of paused, never-submitted tasks."""

from alembic import op

revision = "20261116_0014"
down_revision = "20261115_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_admin_actions_action"), "admin_actions", type_="check")
    op.create_check_constraint(
        "action",
        "admin_actions",
        "action IN ('task.retry_submit', 'task.requery', 'task.retry_transfer', 'task.release', "
        "'text.mark_unknown', 'text.manual_charge', 'text.close_no_charge', "
        "'user.credit_increase', 'user.credit_decrease')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_admin_actions_action"), "admin_actions", type_="check")
    op.create_check_constraint(
        "action",
        "admin_actions",
        "action IN ('task.requery', 'task.retry_transfer', 'task.release', "
        "'text.mark_unknown', 'text.manual_charge', 'text.close_no_charge', "
        "'user.credit_increase', 'user.credit_decrease')",
    )
