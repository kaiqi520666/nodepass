from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["requery", "retry_transfer", "release"]
    reason: str = Field(min_length=4, max_length=240)
    request_id: UUID


class TextResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["mark_unknown", "manual_charge", "close_no_charge"]
    reason: str = Field(min_length=4, max_length=240)
    request_id: UUID
    amount: Decimal | None = Field(default=None, gt=0, lt=Decimal("1e16"))

    @field_validator("amount")
    @classmethod
    def validate_amount_value(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("金额必须是有限数字")
        return value

    @model_validator(mode="after")
    def validate_amount_for_action(self) -> "TextResolveRequest":
        if self.action == "manual_charge":
            if self.amount is None:
                raise ValueError("manual_charge 需要金额")
            if self.amount.as_tuple().exponent < -8:
                raise ValueError("金额最多八位小数")
        elif self.amount is not None:
            raise ValueError("只有 manual_charge 允许金额")
        return self
