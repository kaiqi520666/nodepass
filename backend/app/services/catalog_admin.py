import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.security import credential_cipher
from app.models import Model, ModelPrice, Provider
from app.schemas_catalog import ModelInput, ProviderInput, ProviderSummary

PARAMETERS = {
    "size": "sizes",
    "quality": "qualities",
    "tier": "tiers",
    "series": "series",
    "background": "backgrounds",
    "output_format": "output_formats",
}
RATIOS = ["1:1", "3:2", "16:9", "4:3", "3:4", "5:4", "4:5", "21:9", "9:21", "2:3", "9:16"]
WEB_26_RATIOS = RATIOS + ["1:3", "3:1", "auto"]


def image_profiles() -> list[dict]:
    profiles = []
    for version in ("2", "2.5", "2.6"):
        names = [f"gpt-image-{version}"]
        if version != "2":
            names += [f"gpt-image-{version}-{branch}" for branch in ("flare", "sunburst")]
        fixed = names if version == "2" else names[1:]
        names += [f"{name}-{tier}" for name in fixed for tier in ("1k", "2k", "4k")]
        names += [f"gpt-image-{version}-x"]
        for name in names:
            is_x = name.endswith("-x")
            is_fixed = bool(re.search(r"-[124]k$", name))
            is_26_web = version == "2.6" and name == "gpt-image-2.6"
            configurable = version == "2" or is_x or is_fixed
            profiles.append(
                {
                    "id": name,
                    "family": f"gpt-image-{version}",
                    "sizes": (
                        WEB_26_RATIOS
                        if is_26_web
                        else (RATIOS + (["7:6"] if is_fixed else ["auto"]))
                    )
                    if configurable or is_26_web
                    else [],
                    "qualities": ["low", "medium", "high", "xhigh", "max"]
                    if is_x or is_fixed
                    else [],
                    "tiers": ["web", "1k", "2k", "4k"] if is_x else [],
                    "series": ["flare", "sunburst"] if is_x and version != "2" else [],
                    "backgrounds": ["auto", "opaque", "transparent"] if configurable else [],
                    "output_formats": ["png", "jpeg", "webp"] if is_fixed else [],
                    "max_reference_images": (
                        16 if is_fixed and version != "2" else 9 if configurable else None
                    ),
                }
            )
    return profiles


def invalid(message: str) -> None:
    raise HTTPException(422, message)


def commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "模型 ID 或价格组合已存在，请刷新后检查") from exc


def flush(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "模型 ID 或价格组合已存在，请刷新后检查") from exc


def provider_summary(provider: Provider) -> ProviderSummary:
    return ProviderSummary(
        id=provider.id,
        name=provider.name,
        adapter_key=provider.adapter_key,
        base_url=provider.base_url,
        request_config=provider.request_config,
        is_active=provider.is_active,
        has_credentials=bool(provider.credentials_encrypted),
    )


def save_provider(session: Session, payload: ProviderInput, provider_id: int | None = None):
    provider = session.get(Provider, provider_id) if provider_id else Provider()
    if provider is None:
        raise HTTPException(404, "供应商不存在")
    if provider_id and (
        provider.adapter_key != payload.adapter_key or provider.base_url != payload.base_url
    ):
        invalid("供应商接入身份不可修改，请新建供应商")
    if payload.api_key is not None:
        key = payload.api_key.get_secret_value().strip()
        if not key or any(character.isspace() for character in key):
            invalid("API Key 不能为空或包含空白字符")
        provider.credentials_encrypted = credential_cipher().encrypt(key.encode()).decode("ascii")
    elif not provider_id:
        invalid("新供应商必须填写 API Key")
    provider.name = payload.name
    provider.adapter_key = payload.adapter_key
    provider.base_url = payload.base_url
    provider.request_config = payload.request_config.model_dump()
    provider.is_active = payload.is_active
    session.add(provider)
    commit(session)
    return provider_summary(provider)


def valid_size(value: str, upstream_id: str, profile: dict) -> bool:
    if value in profile["sizes"]:
        return True
    match = re.fullmatch(r"([1-9]\d{0,3})x([1-9]\d{0,3})", value)
    if not match or not re.search(r"-[124]k$", upstream_id):
        return False
    width, height = map(int, match.groups())
    budget = {"1k": 1048576, "2k": 4194304, "4k": 8294400}[upstream_id[-2:]]
    return (
        width % 16 == height % 16 == 0
        and max(width, height) <= 3840
        and max(width, height) <= 3 * min(width, height)
        and 655360 <= width * height <= budget
    )


def validate_model(payload: ModelInput, provider: Provider) -> None:
    if provider.adapter_key != "cangyuan_image":
        invalid("当前仅支持配置沧元图片模型")
    profile = next(
        (item for item in image_profiles() if item["id"] == payload.upstream_model_id), None
    )
    if profile is None:
        invalid("上游模型不在当前已核对的图片型号范围内")
    capabilities = payload.capabilities.model_dump()
    for field in PARAMETERS.values():
        values = capabilities[field]
        if len(set(values)) != len(values):
            invalid(f"{field} 选项不能重复")
        if field == "sizes":
            if any(not valid_size(value, payload.upstream_model_id, profile) for value in values):
                invalid("尺寸不符合该上游型号的比例或像素约束")
        elif not set(values).issubset(profile[field]):
            invalid(f"{field} 包含该上游型号不支持的选项")
    reference_limit = profile["max_reference_images"]
    if reference_limit is not None and capabilities["max_reference_images"] > reference_limit:
        invalid("参考图数量超过该上游型号的上限")
    defaults = capabilities["defaults"]
    if set(defaults) - PARAMETERS.keys():
        invalid("包含不支持的默认参数")
    for parameter, value in defaults.items():
        if value not in capabilities[PARAMETERS[parameter]]:
            invalid(f"{parameter} 默认值必须在已配置的可选值内")
    if payload.is_active:
        for parameter, field in PARAMETERS.items():
            if capabilities[field] and parameter not in defaults:
                invalid(f"上架前请配置 {parameter} 默认值")
        if profile["series"] and not capabilities["series"]:
            invalid("该型号上架前必须配置 series")
        if not payload.prices:
            invalid("上架前至少配置一条价格")
        if not provider.is_active or not provider.credentials_encrypted:
            invalid("上架前请启用供应商并配置密钥")
    dimensions = payload.pricing_dimensions
    if len(set(dimensions)) != len(dimensions):
        invalid("计价维度不能重复")
    if any(not capabilities[PARAMETERS[field]] for field in dimensions):
        invalid("计价维度必须对应已配置的模型能力")
    variants = set()
    price_ids = set()
    for price in payload.prices:
        variant = tuple(sorted(price.variant.items()))
        if variant in variants:
            invalid("价格组合不能重复")
        variants.add(variant)
        if price.id is not None:
            if price.id in price_ids:
                invalid("价目 ID 不能重复")
            price_ids.add(price.id)
        if price.variant and set(price.variant) != set(dimensions):
            invalid("非默认价格必须填写全部计价维度")
        for field, value in price.variant.items():
            if value not in capabilities[PARAMETERS[field]]:
                invalid("价格组合不在已配置的模型能力范围内")
    if payload.is_active and () not in variants:
        default_variant = tuple(sorted((field, defaults[field]) for field in dimensions))
        if default_variant not in variants:
            invalid("默认参数组合没有有效价格，请补充默认价或对应价目")


def model_summary(model: Model) -> dict:
    return {
        "id": model.id,
        "public_id": model.public_id,
        "display_name": model.display_name,
        "media_type": model.media_type,
        "provider_id": model.provider_id,
        "upstream_model_id": model.upstream_model_id,
        "capabilities": model.capabilities,
        "pricing_dimensions": model.pricing_dimensions,
        "is_active": model.is_active,
        "prices": [
            {
                "id": price.id,
                "variant": price.variant,
                "sale_unit": price.sale_unit,
                "sale_unit_price": format(price.sale_unit_price, ".4f"),
                "cost_unit": price.cost_unit,
                "cost_unit_price": format(price.cost_unit_price, ".8f"),
                "cost_currency": price.cost_currency,
            }
            for price in sorted(model.prices, key=lambda price: price.id)
        ],
    }


def save_model(session: Session, payload: ModelInput, model_id: int | None = None):
    provider = session.get(Provider, payload.provider_id)
    if provider is None:
        invalid("供应商不存在")
    validate_model(payload, provider)
    model = (
        session.scalar(
            select(Model).options(selectinload(Model.prices)).where(Model.id == model_id)
        )
        if model_id
        else Model(prices=[])
    )
    if model is None or (model_id and model.media_type != "image"):
        raise HTTPException(404, "图片模型不存在")
    prices = {price.id: price for price in model.prices}
    if any(price.id is not None and price.id not in prices for price in payload.prices):
        invalid("价目不属于当前模型，请刷新后重试")
    if not model_id and any(price.id is not None for price in payload.prices):
        invalid("新模型不能引用已有价目")
    for field, value in payload.model_dump(exclude={"prices"}).items():
        setattr(model, field, value)
    session.add(model)
    flush(session)
    kept = {price.id for price in payload.prices if price.id is not None}
    # Release old JSONB uniqueness slots before writing changed variants in this transaction.
    for price in list(model.prices):
        if price.id not in kept:
            model.prices.remove(price)
            session.delete(price)
        else:
            price.variant = {"_editing_price_id": str(price.id)}
    flush(session)
    for row in payload.prices:
        price = prices[row.id] if row.id is not None else ModelPrice(model_id=model.id)
        for field, value in row.model_dump(exclude={"id"}).items():
            setattr(price, field, value)
        if row.id is None:
            model.prices.append(price)
    commit(session)
    return model_summary(model)
