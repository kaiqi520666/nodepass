from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps


class User(Timestamps, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    email_normalized: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    account: Mapped["CreditAccount"] = relationship(back_populates="user", uselist=False)


class CreditAccount(Timestamps, Base):
    __tablename__ = "credit_accounts"
    __table_args__ = (
        CheckConstraint("available >= 0 AND available < 'Infinity'::numeric", name="available"),
        CheckConstraint("frozen >= 0 AND frozen < 'Infinity'::numeric", name="frozen"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    available: Mapped[Decimal] = mapped_column(Numeric(20, 4), server_default="0.0000")
    frozen: Mapped[Decimal] = mapped_column(Numeric(20, 4), server_default="0.0000")
    user: Mapped[User] = relationship(back_populates="account")


class ApiKey(Timestamps, Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    key_prefix: Mapped[str] = mapped_column(String(24))
    key_digest: Mapped[str] = mapped_column(String(64), unique=True)
    key_encrypted: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
