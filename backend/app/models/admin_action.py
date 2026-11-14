from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdminAction(Base):
    __tablename__ = "admin_actions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('task.requery', 'task.retry_transfer', 'task.release', "
            "'text.mark_unknown', 'text.manual_charge', 'text.close_no_charge', "
            "'user.credit_increase', 'user.credit_decrease')",
            name="action",
        ),
        CheckConstraint(
            "target_type IN ('task', 'text_call', 'user')",
            name="target_type",
        ),
        CheckConstraint(
            "amount IS NULL OR (amount >= 0 AND amount < 'Infinity'::numeric)",
            name="amount",
        ),
        Index("ix_admin_actions_target", "target_type", "target_id", "created_at"),
        Index("ix_admin_actions_actor", "actor_user_id", "created_at"),
        Index("ix_admin_actions_action", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40))
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), unique=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(240))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    credit_entry_id: Mapped[int | None] = mapped_column(ForeignKey("credit_entries.id"))
    before_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    after_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
