from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer, model_validator


class CatalogInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProviderConfig(CatalogInput):
    timeout_seconds: int = Field(default=60, gt=0, strict=True)
    poll_interval_seconds: int = Field(default=5, gt=0, strict=True)
    task_timeout_seconds: int = Field(default=1800, gt=0, strict=True)


class ProviderInput(CatalogInput):
    name: str = Field(min_length=1, max_length=120)
    adapter_key: Literal["cangyuan_image", "meaicc_video", "modelgate_openai"] = "cangyuan_image"
    base_url: str = "https://direct-api.cangyuansuanli.cn"
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    request_config: ProviderConfig = Field(default_factory=ProviderConfig)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_address(self):
        addresses = {
            "cangyuan_image": "https://direct-api.cangyuansuanli.cn",
            "meaicc_video": "https://api.meaicc.com",
            "modelgate_openai": "https://intl.modelgate.top",
        }
        if self.base_url != addresses[self.adapter_key]:
            raise ValueError("供应商接口地址与接入方式不匹配")
        return self


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
    max_reference_images: int = Field(default=0, ge=0, strict=True)
    supports_mask: bool = False
    defaults: dict[str, str] = Field(default_factory=dict, max_length=6)


class VideoCapabilities(CatalogInput):
    family: str = ""
    version: str = ""
    resolutions: list[str] = Field(default_factory=list)
    aspect_ratios: list[str] = Field(default_factory=list)
    min_seconds: Decimal = Field(gt=0, allow_inf_nan=False)
    max_seconds: Decimal = Field(gt=0, allow_inf_nan=False)
    max_reference_images: int = Field(default=0, ge=0, strict=True)
    max_reference_videos: int = Field(default=0, ge=0, strict=True)
    max_reference_audios: int = Field(default=0, ge=0, strict=True)
    supports_first_frame: bool = False
    supports_last_frame: bool = False
    defaults: dict[str, str] = Field(default_factory=dict)


class PriceInput(CatalogInput):
    id: int | None = Field(default=None, gt=0)
    variant: dict[str, str] = Field(default_factory=dict, max_length=4)
    sale_unit: Literal["image", "video", "second"] = "image"
    sale_unit_price: Decimal = Field(ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)
    cost_unit: Literal["image", "video", "second"] = "image"
    cost_unit_price: Decimal = Field(ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)


class TokenPriceInput(CatalogInput):
    input_price: Decimal = Field(ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)
    output_price: Decimal = Field(ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)
    cache_read_price: Decimal = Field(ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)
    cost_multiplier: Decimal = Field(ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)
    sale_multiplier: Decimal = Field(ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)
    long_context_threshold: int = Field(gt=0, strict=True)
    long_context_input_multiplier: Decimal = Field(
        ge=1, max_digits=24, decimal_places=8, allow_inf_nan=False
    )
    long_context_output_multiplier: Decimal = Field(
        ge=1, max_digits=24, decimal_places=8, allow_inf_nan=False
    )

    @field_serializer(
        "input_price",
        "output_price",
        "cache_read_price",
        "cost_multiplier",
        "sale_multiplier",
        "long_context_input_multiplier",
        "long_context_output_multiplier",
        when_used="json",
    )
    def serialize_price(self, value: Decimal):
        return format(value, ".8f")


class TextCapabilities(CatalogInput):
    family: str = "gpt"
    input_modalities: list[Literal["text", "image"]] = Field(
        default_factory=lambda: ["text", "image"]
    )


class ModelInput(CatalogInput):
    public_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    display_name: str = Field(min_length=1, max_length=160)
    media_type: Literal["image", "video", "text"] = "image"
    provider_id: int = Field(gt=0)
    upstream_model_id: str = Field(min_length=1, max_length=160)
    capabilities: ImageCapabilities | VideoCapabilities | TextCapabilities = Field(
        default_factory=ImageCapabilities
    )
    token_price: TokenPriceInput | None = None
    pricing_dimensions: list[Literal["tier", "quality", "series", "size"]] = Field(
        default_factory=list, max_length=4
    )
    prices: list[PriceInput] = Field(default_factory=list, max_length=300)
    is_active: bool = False
