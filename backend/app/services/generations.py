from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.money import money
from app.models import CreditAccount, CreditEntry, Model, Provider, Task, User
from app.schemas import (
    ImageEditRequest,
    ImageGenerationRequest,
    QueuedImageGeneration,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from app.schemas_catalog import ProviderConfig
from app.services.media import validate_https_url

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
    return resolved


def _find_price(model: Model, resolved: dict[str, Any]):
    dimensions = model.pricing_dimensions or []
    variant = {dimension: resolved[dimension] for dimension in dimensions}
    prices = [price for price in model.prices if price.sale_unit == "image"]
    exact = next((price for price in prices if price.variant == variant), None)
    if exact:
        return exact, variant
    invalid("没有匹配当前参数的价格")


def _snapshot(model: Model, price) -> dict[str, Any]:
    return {
        "public_id": model.public_id,
        "display_name": model.display_name,
        "media_type": model.media_type,
        "provider_id": model.provider_id,
        "upstream_model_id": model.upstream_model_id,
        "price_id": price.id,
        "sale_unit_price": format(price.sale_unit_price, ".8f"),
        "cost_unit_price": format(price.cost_unit_price, ".8f"),
        "sale_unit": price.sale_unit,
        "cost_unit": price.cost_unit,
    }


def _load_model(session: Session, public_id: str, media_type: str) -> tuple[Model, Provider]:
    result = session.execute(
        select(Model, Provider)
        .options(joinedload(Model.prices))
        .join(Provider, Model.provider_id == Provider.id)
        .where(Model.public_id == public_id, Model.media_type == media_type)
    ).first()
    if result is None:
        raise HTTPException(404, "Model not found.")
    model, provider = result
    if not model.is_active or not provider.is_active:
        raise HTTPException(503, "Model provider is unavailable.")
    return model, provider


def _freeze(
    session: Session,
    user: User,
    model: Model,
    provider: Provider,
    price,
    params: dict[str, Any],
    quantity: Decimal,
    cost_quantity: Decimal,
) -> Task:
    with localcontext() as context:
        context.prec = 64
        amount = money(price.sale_unit_price * quantity)
        cost = (price.cost_unit_price * cost_quantity).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        )
    if amount >= Decimal("1e16") or cost >= Decimal("1e16"):
        invalid("计费金额超出数据库字段精度")
    account = session.scalar(
        select(CreditAccount).where(CreditAccount.user_id == user.id).with_for_update()
    )
    if account is None:
        raise HTTPException(409, "Credit account is not initialized.")
    if account.available < amount:
        raise HTTPException(402, "Insufficient credit balance.")
    now = datetime.now(UTC)
    config = ProviderConfig.model_validate(provider.request_config).model_dump()
    task = Task(
        user_id=user.id,
        model_id=model.id,
        provider_id=provider.id,
        price_id=price.id,
        status="queued",
        billing_status="held",
        request_params=params,
        model_snapshot=_snapshot(model, price),
        provider_snapshot={
            "id": provider.id,
            "name": provider.name,
            "adapter_key": provider.adapter_key,
            "base_url": provider.base_url,
            "request_config": config,
        },
        quantity=quantity,
        frozen_amount=amount,
        cost_amount=cost,
        deadline_at=now + timedelta(seconds=config["task_timeout_seconds"]),
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
            description=f"生成任务冻结：{model.public_id}",
        )
    )
    session.commit()
    return task


def create_image_task(
    session: Session, user: User, payload: ImageGenerationRequest
) -> QueuedImageGeneration:
    model, provider = _load_model(session, payload.model, "image")
    if isinstance(payload, ImageEditRequest):
        caps = model.capabilities or {}
        if len(payload.images) > caps.get("max_reference_images", 0):
            invalid("参考图超过模型配置的 max_reference_images")
        if payload.mask is not None and not caps.get("supports_mask", False):
            invalid("当前模型不支持 mask")
        references = [*payload.images, *([payload.mask] if payload.mask else [])]
        for reference in references:
            try:
                validate_https_url(reference.image_url)
            except ValueError as exc:
                invalid(str(exc))
    resolved = _resolve_request(payload, model)
    price, variant = _find_price(model, resolved)
    params = payload.model_dump(exclude_none=True)
    params.update(resolved)
    params["price_variant"] = variant
    task = _freeze(
        session, user, model, provider, price, params, Decimal(payload.n), Decimal(payload.n)
    )
    return QueuedImageGeneration(
        id=task.task_id,
        model=model.public_id,
        created=int(task.created_at.timestamp()),
    )


def create_video_task(
    session: Session, user: User, payload: VideoGenerationRequest
) -> VideoGenerationResponse:
    model, provider = _load_model(session, payload.model, "video")
    price = next(
        (row for row in model.prices if row.variant == {} and row.sale_unit in {"video", "second"}),
        None,
    )
    if price is None or model.pricing_dimensions:
        invalid("没有匹配当前参数的价格")
    caps = model.capabilities
    defaults = caps["defaults"]
    if price.sale_unit == "second" and payload.seconds is None:
        invalid("按秒计费模型必须提供 seconds")
    seconds = payload.seconds if payload.seconds is not None else Decimal(defaults["seconds"])
    if not Decimal(str(caps["min_seconds"])) <= seconds <= Decimal(str(caps["max_seconds"])):
        invalid("seconds 不在模型支持的时长范围内")
    params = payload.model_dump(mode="json", exclude_none=True)
    params["seconds"] = str(seconds)
    params["price_variant"] = {}
    for field, choices in (("resolution", "resolutions"), ("aspect_ratio", "aspect_ratios")):
        value = getattr(payload, field) or defaults[field]
        if value not in caps[choices]:
            invalid(f"{field} 不支持该参数值")
        params[field] = value
    counts = {
        kind: sum(item.type == kind for item in payload.references)
        for kind in (
            "first_frame",
            "last_frame",
            "reference_image",
            "reference_video",
            "reference_audio",
        )
    }
    for kind in ("first_frame", "last_frame"):
        if counts[kind] > 1 or (counts[kind] and not caps[f"supports_{kind}"]):
            invalid(f"{kind} 不受支持或重复")
    image_count = counts["reference_image"] + counts["first_frame"] + counts["last_frame"]
    for count, field in (
        (image_count, "max_reference_images"),
        (counts["reference_video"], "max_reference_videos"),
        (counts["reference_audio"], "max_reference_audios"),
    ):
        if count > caps[field]:
            invalid(f"参考素材超过模型配置的 {field}")
    for item in payload.references:
        try:
            validate_https_url(item.url)
        except ValueError as exc:
            invalid(str(exc))
    task = _freeze(
        session,
        user,
        model,
        provider,
        price,
        params,
        seconds if price.sale_unit == "second" else Decimal(1),
        seconds if price.cost_unit == "second" else Decimal(1),
    )
    return VideoGenerationResponse(
        id=task.task_id,
        model=model.public_id,
        status=task.status,
        created=int(task.created_at.timestamp()),
        completed=None,
    )
