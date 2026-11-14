from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps


class TextCall(Timestamps, Base):
    __tablename__ = "text_calls"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'succeeded', 'failed', 'usage_unknown', "
            "'settled_manually', 'closed_no_charge')",
            name="status",
        ),
        CheckConstraint(
            "resolution IS NULL OR resolution IN "
            "('manual_marked_unknown', 'manual_charged', 'manual_closed_no_charge')",
            name="resolution",
        ),
        Index("ix_text_calls_status_updated_at", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    endpoint: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24))
    price_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    usage: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    charge_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    error_message: Mapped[str | None] = mapped_column(String(240))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(32))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    late_usage: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    late_usage_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
