from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_serializer


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)


class AccountSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    available: Decimal
    frozen: Decimal

    @field_serializer("available", "frozen")
    def serialize_credit(self, value: Decimal):
        return format(value, ".8f")


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    account: AccountSummary


class DailyConsumption(BaseModel):
    date: str
    consumed: Decimal

    @field_serializer("consumed")
    def serialize_consumed(self, value: Decimal):
        return format(value, ".8f")


class DashboardSummary(BaseModel):
    available: Decimal
    consumed: Decimal
    requests: int
    today_consumed: Decimal
    trend: list[DailyConsumption]

    @field_serializer("available", "consumed", "today_consumed")
    def serialize_credit(self, value: Decimal):
        return format(value, ".8f")


class TextCallSummary(BaseModel):
    id: UUID
    model: str
    status: Literal[
        "processing",
        "succeeded",
        "failed",
        "usage_unknown",
        "settled_manually",
        "closed_no_charge",
    ]
    created: int
    completed: int | None
    duration_ms: int
    input_tokens: int | None
    output_tokens: int | None
    charge_amount: Decimal | None

    @field_serializer("charge_amount")
    def serialize_charge(self, value: Decimal | None):
        return format(value, ".8f") if value is not None else None


class TextCallPage(BaseModel):
    data: list[TextCallSummary]
    total: int
    models: list[str]


class TextSalePrice(BaseModel):
    input_price: Decimal
    output_price: Decimal
    cache_read_price: Decimal
    sale_multiplier: Decimal
    long_context_threshold: int
    long_context_input_multiplier: Decimal
    long_context_output_multiplier: Decimal

    @field_serializer(
        "input_price",
        "output_price",
        "cache_read_price",
        "sale_multiplier",
        "long_context_input_multiplier",
        "long_context_output_multiplier",
    )
    def serialize_price(self, value: Decimal):
        return format(value, ".8f")


class TextCallDetail(TextCallSummary):
    endpoint: str
    stream: bool | None
    usage: dict[str, int] | None
    sale_price: TextSalePrice
    error_message: str | None


class PublicPrice(BaseModel):
    variant: dict[str, str]
    unit: Literal["image", "video", "second"]
    unit_price: Decimal

    @field_serializer("unit_price")
    def serialize_price(self, value: Decimal):
        return format(value, ".8f")


class PublicModel(BaseModel):
    id: str
    name: str
    media_type: Literal["image", "video", "text"]
    capabilities: dict[str, Any]
    prices: list[PublicPrice]
    token_prices: dict[str, Decimal] | None = None
    long_context_threshold: int | None = None
    long_context_token_prices: dict[str, Decimal] | None = None

    @field_serializer("token_prices", "long_context_token_prices")
    def serialize_token_prices(self, value: dict[str, Decimal] | None):
        return {field: format(price, ".8f") for field, price in value.items()} if value else None


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    expires_at: datetime | None = None


class ApiKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    expires_at: datetime | None = None


class ApiKeySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeySummary):
    key: str


class ApiKeySecret(BaseModel):
    key: str


class CreditAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    direction: Literal["increase", "decrease"]
    amount: Decimal = Field(gt=0, lt=Decimal("1e16"), allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=240)
    request_id: UUID | None = None


class AdminPasswordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: SecretStr = Field(min_length=8, max_length=128)


class OpenAIModel(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str = "nodepass"


class OpenAIModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[OpenAIModel]


class ImageGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    model: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1)
    n: int = Field(default=1, ge=1, le=1, strict=True)
    size: str | None = Field(default=None, min_length=1)
    quality: str | None = Field(default=None, min_length=1)
    tier: str | None = Field(default=None, min_length=1)
    series: str | None = Field(default=None, min_length=1)
    background: str | None = Field(default=None, min_length=1)
    output_format: str | None = Field(default=None, min_length=1)
    response_format: Literal["url", "b64_json"] | None = None
    user: str | None = None


class ImageReference(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    image_url: str = Field(min_length=1)


class ImageEditRequest(ImageGenerationRequest):
    images: list[ImageReference] = Field(min_length=1)
    mask: ImageReference | None = None
    response_format: Literal["url"] | None = None


class QueuedImageGeneration(BaseModel):
    id: UUID
    object: Literal["image.generation"] = "image.generation"
    status: Literal["queued"] = "queued"
    model: str
    created: int
    data: list[Any] = Field(default_factory=list)


class ImageGenerationResponse(BaseModel):
    id: UUID
    object: Literal["image.generation"] = "image.generation"
    status: str
    model: str
    created: int
    completed: int | None = None
    data: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, str] | None = None


class VideoReference(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Literal[
        "first_frame", "last_frame", "reference_image", "reference_video", "reference_audio"
    ]
    url: str = Field(min_length=1)


class VideoGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    model: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1)
    seconds: Decimal | None = Field(
        default=None, gt=0, allow_inf_nan=False, max_digits=24, decimal_places=8
    )
    resolution: str | None = Field(default=None, min_length=1)
    aspect_ratio: str | None = Field(default=None, min_length=1)
    references: list[VideoReference] = Field(default_factory=list)


class VideoGenerationResponse(BaseModel):
    id: UUID
    object: Literal["video.generation"] = "video.generation"
    status: str
    model: str
    created: int
    completed: int | None = None
    timed_out: bool = False
    data: list[dict[str, str]] = Field(default_factory=list)
    error: dict[str, str] | None = None


class OssSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    endpoint: str = Field(min_length=1, max_length=2048)
    region: str = Field(min_length=1, max_length=128)
    bucket: str = Field(min_length=1, max_length=128)
    access_key_id: str = Field(min_length=1, max_length=256)
    access_key_secret: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    public_base_url: str = Field(min_length=1, max_length=2048)
    object_prefix: str = Field(default="generated", max_length=256)
    is_active: bool = True


class OssSettingsSummary(BaseModel):
    endpoint: str = ""
    region: str = ""
    bucket: str = ""
    access_key_id: str = ""
    public_base_url: str = ""
    object_prefix: str = "generated"
    is_active: bool = False
    has_credentials: bool = False


class OssTestResult(BaseModel):
    ok: bool
    message: str
    object_key: str | None = None
    elapsed_ms: int | None = None


class TaskSummary(BaseModel):
    id: UUID
    object: Literal["image.generation", "video.generation"] = "image.generation"
    status: str
    model: str
    model_name: str
    media_type: Literal["image", "video"]
    created: int
    billing_status: str
    frozen_amount: Decimal
    consumed_amount: Decimal
    completed: int | None = None
    duration_ms: int | None = None
    timed_out: bool = False
    request_params: dict[str, Any] = Field(default_factory=dict)
    upstream_status: str | None = None
    error_message: str | None = None
    resolution: str | None = None
    data: list[dict[str, Any]] = Field(default_factory=list)

    @field_serializer("frozen_amount", "consumed_amount")
    def serialize_amount(self, value: Decimal):
        return format(value, ".8f")
