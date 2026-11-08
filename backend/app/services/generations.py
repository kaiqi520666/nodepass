from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import CreditAccount, CreditEntry, Model, Provider, Task, User
from app.schemas import ImageGenerationRequest, QueuedImageGeneration

MONEY_QUANTUM = Decimal("0.0001")
CAPABILITY_FIELDS = {
    "size": "sizes",
    "quality": "qualities",
    "tier": "tiers",
    "series": "series",
    "background": "backgrounds",
    "output_format": "output_formats",
}


def invalid(message: str) -> None:
    raise HTTPException(422, message)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _resolve_request(payload: ImageGenerationRequest, model: Model) -> dict[str, Any]:
    capabilities = model.capabilities or {}
    resolved: dict[str, Any] = {}
    for parameter, field in CAPABILITY_FIELDS.items():
        value = getattr(payload, parameter)
        allowed = capabilities.get(field, [])
        if value is not None:
            if not allowed or value not in allowed:
                invalid(f"{parameter} 不支持该参数值")
            resolved[parameter] = value
            continue
        default = (capabilities.get("defaults") or {}).get(parameter)
        if default is not None:
            if allowed and default not in allowed:
                invalid(f"{parameter} 默认值无效")
            resolved[parameter] = default
    for dimension in model.pricing_dimensions or []:
        if dimension not in resolved:
            invalid(f"请提供计价参数 {dimension}")
    explicit_variant = {
        dimension: getattr(payload, dimension)
        for dimension in model.pricing_dimensions or []
        if getattr(payload, dimension) is not None
    }
    resolved["_explicit_variant"] = explicit_variant
    return resolved


def _find_price(model: Model, resolved: dict[str, Any]):
    dimensions = model.pricing_dimensions or []
    explicit_variant = resolved.pop("_explicit_variant")
    variant = {dimension: resolved[dimension] for dimension in dimensions}
    prices = [price for price in model.prices if price.sale_unit == "image"]
    exact = next((price for price in prices if price.variant == variant), None)
    if exact:
        return exact, variant
    if not explicit_variant:
        default = next((price for price in prices if not price.variant), None)
        if default:
            return default, {}
    invalid("没有匹配当前参数的价格")


def _snapshot(model: Model, price) -> dict[str, Any]:
    return {
        "public_id": model.public_id,
        "display_name": model.display_name,
        "media_type": model.media_type,
        "provider_id": model.provider_id,
        "upstream_model_id": model.upstream_model_id,
        "price_id": price.id,
        "sale_unit_price": format(price.sale_unit_price, ".4f"),
        "cost_unit_price": format(price.cost_unit_price, ".8f"),
        "cost_currency": price.cost_currency,
    }


def create_image_task(
    session: Session, user: User, payload: ImageGenerationRequest
) -> QueuedImageGeneration:
    result = session.execute(
        select(Model, Provider)
        .options(joinedload(Model.prices))
        .join(Provider, Model.provider_id == Provider.id)
        .where(Model.public_id == payload.model, Model.media_type == "image")
    ).first()
    if result is None:
        raise HTTPException(404, "Model not found.")
    model, provider = result
    if not model.is_active or not provider.is_active:
        raise HTTPException(503, "Model provider is unavailable.")
    resolved = _resolve_request(payload, model)
    price, variant = _find_price(model, resolved)
    amount = _money(price.sale_unit_price * payload.n)
    account = session.scalar(
        select(CreditAccount).where(CreditAccount.user_id == user.id).with_for_update()
    )
    if account is None:
        raise HTTPException(409, "Credit account is not initialized.")
    if account.available < amount:
        raise HTTPException(402, "Insufficient credit balance.")
    now = datetime.now(UTC)
    request_params = payload.model_dump(exclude_none=True)
    request_params.update(
        {key: value for key, value in resolved.items() if not key.startswith("_")}
    )
    request_params["price_variant"] = variant
    task = Task(
        user_id=user.id,
        model_id=model.id,
        provider_id=provider.id,
        price_id=price.id,
        status="queued",
        billing_status="held",
        request_params=request_params,
        model_snapshot=_snapshot(model, price),
        provider_snapshot={
            "id": provider.id,
            "name": provider.name,
            "adapter_key": provider.adapter_key,
            "base_url": provider.base_url,
            "request_config": provider.request_config,
        },
        quantity=payload.n,
        frozen_amount=amount,
        cost_amount=price.cost_unit_price * payload.n,
        cost_currency=price.cost_currency,
        deadline_at=now + timedelta(minutes=30),
        next_run_at=now,
    )
    account.available -= amount
    account.frozen += amount
    session.add(task)
    session.flush()
    session.add(
        CreditEntry(
            user_id=user.id,
            task_id=task.id,
            entry_type="freeze",
            idempotency_key=f"task:{task.task_id}:freeze",
            amount=amount,
            available_delta=-amount,
            frozen_delta=amount,
            description=f"图片生成冻结：{model.public_id}",
        )
    )
    session.commit()
    return QueuedImageGeneration(
        id=task.task_id,
        model=model.public_id,
        created=int(now.timestamp()),
    )
