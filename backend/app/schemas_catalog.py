from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class CatalogInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProviderConfig(CatalogInput):
    timeout_seconds: int = Field(default=60, ge=10, le=600, strict=True)
    poll_interval_seconds: int = Field(default=5, ge=5, le=60, strict=True)


class ProviderInput(CatalogInput):
    name: str = Field(min_length=1, max_length=120)
    adapter_key: Literal["cangyuan_image"] = "cangyuan_image"
    base_url: Literal["https://direct-api.cangyuansuanli.cn"] = (
        "https://direct-api.cangyuansuanli.cn"
    )
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    request_config: ProviderConfig = Field(default_factory=ProviderConfig)
    is_active: bool = True


class ProviderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    adapter_key: str
    base_url: str
    request_config: ProviderConfig
    is_active: bool
    has_credentials: bool


class ImageCapabilities(CatalogInput):
    sizes: list[str] = Field(default_factory=list, max_length=64)
    qualities: list[str] = Field(default_factory=list, max_length=5)
    tiers: list[str] = Field(default_factory=list, max_length=4)
    series: list[str] = Field(default_factory=list, max_length=2)
    backgrounds: list[str] = Field(default_factory=list, max_length=3)
    output_formats: list[str] = Field(default_factory=list, max_length=3)
    max_reference_images: int = Field(default=0, ge=0, le=16, strict=True)
    supports_mask: bool = False
    defaults: dict[str, str] = Field(default_factory=dict, max_length=6)


class PriceInput(CatalogInput):
    id: int | None = Field(default=None, gt=0)
    variant: dict[str, str] = Field(default_factory=dict, max_length=4)
    sale_unit: Literal["image"] = "image"
    sale_unit_price: Decimal = Field(ge=0, max_digits=20, decimal_places=4, allow_inf_nan=False)
    cost_unit: Literal["image"] = "image"
    cost_unit_price: Decimal = Field(ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)
    cost_currency: Literal["CNY", "USD"]


class ModelInput(CatalogInput):
    public_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    display_name: str = Field(min_length=1, max_length=160)
    media_type: Literal["image"] = "image"
    provider_id: int = Field(gt=0)
    upstream_model_id: str = Field(min_length=1, max_length=160)
    capabilities: ImageCapabilities = Field(default_factory=ImageCapabilities)
    pricing_dimensions: list[Literal["tier", "quality", "series", "size"]] = Field(
        default_factory=list, max_length=4
    )
    prices: list[PriceInput] = Field(default_factory=list, max_length=300)
    is_active: bool = False
