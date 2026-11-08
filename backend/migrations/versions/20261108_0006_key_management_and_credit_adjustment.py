"""Add API key management fields and admin credit adjustments."""

import sqlalchemy as sa
from alembic import op

revision = "20261108_0006"
down_revision = "20261108_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("key_encrypted", sa.String(512)))
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.execute(
        sa.text("ALTER TABLE credit_entries DROP CONSTRAINT IF EXISTS ck_credit_entries_entry_type")
    )
    op.execute(
        sa.text(
            "ALTER TABLE credit_entries ADD CONSTRAINT ck_credit_entries_entry_type "
            "CHECK (entry_type IN ('freeze', 'settle', 'release', 'refund', 'recharge', "
            "'admin_credit', 'admin_debit'))"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE credit_entries DROP CONSTRAINT IF EXISTS ck_credit_entries_entry_type")
    )
    op.execute(
        sa.text(
            "ALTER TABLE credit_entries ADD CONSTRAINT ck_credit_entries_entry_type "
            "CHECK (entry_type IN ('freeze', 'settle', 'release', 'refund', 'recharge'))"
        )
    )
    op.drop_column("api_keys", "expires_at")
    op.drop_column("api_keys", "key_encrypted")
