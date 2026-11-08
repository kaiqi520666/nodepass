"""Backfill media type in task snapshots."""

from alembic import op

revision = "20261108_0008"
down_revision = "20261108_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE tasks
        SET model_snapshot = jsonb_set(
            tasks.model_snapshot,
            '{media_type}',
            to_jsonb(models.media_type),
            true
        )
        FROM models
        WHERE tasks.model_id = models.id
          AND NOT (tasks.model_snapshot ? 'media_type')
        """
    )


def downgrade() -> None:
    op.execute("UPDATE tasks SET model_snapshot = model_snapshot - 'media_type'")
