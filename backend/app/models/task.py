from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps


class Task(Timestamps, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'submitting', 'submission_unknown', 'pending', "
            "'processing', 'transferring', 'succeeded', 'failed')",
            name="status",
        ),
        CheckConstraint(
            "billing_status IN ('held', 'settled', 'released', 'refunded')",
            name="billing_status",
        ),
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint(
            "frozen_amount >= 0 AND frozen_amount < 'Infinity'::numeric", name="frozen"
        ),
        Index("ix_tasks_status_next_run_at", "status", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), default=uuid4, unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    price_id: Mapped[int] = mapped_column(ForeignKey("model_prices.id"))
    status: Mapped[str] = mapped_column(String(32), server_default="queued")
    billing_status: Mapped[str] = mapped_column(String(16), server_default="held")
    request_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default="{}", nullable=False
    )
    model_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default="{}", nullable=False
    )
    provider_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default="{}", nullable=False
    )
    result_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default="[]", nullable=False
    )
    upstream_task_id: Mapped[str | None] = mapped_column(String(200))
    upstream_status: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), server_default="1")
    frozen_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    timed_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    upstream_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_required: Mapped[bool] = mapped_column(server_default="false")
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)

    def has_timed_out(self, now: datetime) -> bool:
        end = self.completed_at or now
        return self.timed_out_at is not None or bool(self.deadline_at and end >= self.deadline_at)

    ledger_entries: Mapped[list["CreditEntry"]] = relationship(back_populates="task")
    task_assets: Mapped[list["TaskAsset"]] = relationship(back_populates="task")


class Asset(Timestamps, Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    source_url_encrypted: Mapped[str | None] = mapped_column(Text)
    oss_region: Mapped[str | None] = mapped_column(String(128))
    oss_bucket: Mapped[str | None] = mapped_column(String(128))
    oss_object_key: Mapped[str | None] = mapped_column(String(1024))
    public_url: Mapped[str | None] = mapped_column(String(2048))
    content_type: Mapped[str | None] = mapped_column(String(160))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(128))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task_assets: Mapped[list["TaskAsset"]] = relationship(back_populates="asset")


class TaskAsset(Base):
    __tablename__ = "task_assets"
    __table_args__ = (UniqueConstraint("task_id", "role", "asset_id"),)

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)

    task: Mapped[Task] = relationship(back_populates="task_assets")
    asset: Mapped[Asset] = relationship(back_populates="task_assets")


class CreditEntry(Timestamps, Base):
    __tablename__ = "credit_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('freeze', 'settle', 'release', 'refund', 'recharge', "
            "'admin_credit', 'admin_debit', 'text_charge')",
            name="entry_type",
        ),
        CheckConstraint(
            "available_delta > '-Infinity'::numeric AND available_delta < 'Infinity'::numeric",
            name="available_delta",
        ),
        CheckConstraint(
            "frozen_delta > '-Infinity'::numeric AND frozen_delta < 'Infinity'::numeric",
            name="frozen_delta",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    available_delta: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    frozen_delta: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    description: Mapped[str] = mapped_column(String(240))

    task: Mapped[Task | None] = relationship(back_populates="ledger_entries")
