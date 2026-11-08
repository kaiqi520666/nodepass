"""Require encrypted API key storage."""

import sqlalchemy as sa
from alembic import op

revision = "20261108_0007"
down_revision = "20261108_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("api_keys", "key_encrypted", existing_type=sa.String(512), nullable=False)


def downgrade() -> None:
    op.alter_column("api_keys", "key_encrypted", existing_type=sa.String(512), nullable=True)
