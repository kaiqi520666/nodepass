from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)


class AccountSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    available: Decimal
    frozen: Decimal


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    account: AccountSummary


class PublicPrice(BaseModel):
    variant: dict[str, str]
    unit: Literal["image", "video", "second"]
    unit_price: Decimal


class PublicModel(BaseModel):
    id: str
    name: str
    media_type: Literal["image", "video"]
    capabilities: dict[str, Any]
    prices: list[PublicPrice]


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
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=240)


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
    object: Literal["image.generation"] = "image.generation"
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
    data: list[dict[str, Any]] = Field(default_factory=list)
