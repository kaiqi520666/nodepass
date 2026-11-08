from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps


class Provider(Timestamps, Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    adapter_key: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str] = mapped_column(String(2048))
    credentials_encrypted: Mapped[str] = mapped_column(Text)
    request_config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Model(Timestamps, Base):
    __tablename__ = "models"
    __table_args__ = (
        CheckConstraint("media_type IN ('image', 'video')", name="media_type"),
        CheckConstraint("jsonb_typeof(capabilities) = 'object'", name="capabilities"),
        CheckConstraint("jsonb_typeof(pricing_dimensions) = 'array'", name="pricing_dimensions"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(String(160), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    media_type: Mapped[str] = mapped_column(String(16))
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    upstream_model_id: Mapped[str] = mapped_column(String(160))
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    pricing_dimensions: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="false")
    prices: Mapped[list["ModelPrice"]] = relationship(back_populates="model")


class ModelPrice(Timestamps, Base):
    __tablename__ = "model_prices"
    __table_args__ = (
        UniqueConstraint("model_id", "variant"),
        CheckConstraint("jsonb_typeof(variant) = 'object'", name="variant"),
        CheckConstraint("sale_unit IN ('image', 'video', 'second')", name="sale_unit"),
        CheckConstraint(
            "sale_unit_price >= 0 AND sale_unit_price < 'Infinity'::numeric", name="sale_price"
        ),
        CheckConstraint(
            "cost_unit_price >= 0 AND cost_unit_price < 'Infinity'::numeric", name="cost_price"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    variant: Mapped[dict[str, str]] = mapped_column(JSONB, server_default="{}")
    sale_unit: Mapped[str] = mapped_column(String(16))
    sale_unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    cost_unit: Mapped[str] = mapped_column(String(32))
    cost_unit_price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    cost_currency: Mapped[str] = mapped_column(String(16))
    model: Mapped[Model] = relationship(back_populates="prices")
