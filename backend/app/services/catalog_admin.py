from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.security import credential_cipher
from app.models import Model, ModelPrice, Provider, TokenPrice
from app.schemas_catalog import (
    ImageCapabilities,
    ModelInput,
    ProviderInput,
    ProviderSummary,
    TextCapabilities,
    TokenPriceInput,
    VideoCapabilities,
)
from app.services.video_catalog import video_profiles

PARAMETERS = {
    "size": "sizes",
    "quality": "qualities",
    "tier": "tiers",
    "series": "series",
    "background": "backgrounds",
    "output_format": "output_formats",
}
RATIOS = ["1:1", "3:2", "16:9", "4:3", "3:4", "5:4", "4:5", "21:9", "9:21", "2:3", "9:16"]


def image_profiles() -> list[dict]:
    return [
        {
            "id": "gpt-image-2-x",
            "family": "gpt-image-2",
            "sizes": RATIOS + ["auto"],
            "qualities": ["low", "medium", "high", "xhigh", "max"],
            "tiers": ["web", "1k", "2k", "4k"],
            "series": [],
            "backgrounds": ["auto", "opaque", "transparent"],
            "output_formats": [],
            "max_reference_images": 9,
        },
        {
            "id": "gpt-image-2.5-x",
            "family": "gpt-image-2.5",
            "sizes": RATIOS + ["auto"],
            "qualities": ["low", "medium", "high", "xhigh", "max"],
            "tiers": ["web", "1k", "2k", "4k"],
            "series": ["flare", "sunburst"],
            "backgrounds": ["auto", "opaque", "transparent"],
            "output_formats": [],
            "max_reference_images": 9,
        },
    ]


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


def validate_model(payload: ModelInput, provider: Provider) -> None:
    if payload.media_type == "text":
        if provider.adapter_key != "modelgate_openai":
            invalid("文本模型必须使用 GPT 供应商")
        if payload.upstream_model_id != "gpt-6.1-sol":
            invalid("上游模型不在当前已核对的文本型号范围内")
        if not isinstance(payload.capabilities, TextCapabilities) or not payload.token_price:
            invalid("文本模型必须配置文本能力与 token 价格")
        if "text" not in payload.capabilities.input_modalities:
            invalid("文本模型必须支持文本输入")
        if payload.prices or payload.pricing_dimensions:
            invalid("文本模型使用 token 价格，不使用图片视频价目")
        if payload.is_active and (not provider.is_active or not provider.credentials_encrypted):
            invalid("上架前请启用供应商并配置密钥")
        return
    if payload.token_price is not None:
        invalid("图片视频模型不使用 token 价格")
    if payload.media_type == "video":
        validate_video_model(payload, provider)
        return
    if not isinstance(payload.capabilities, ImageCapabilities):
        invalid("图片模型必须使用图片能力参数")
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
        if not set(values).issubset(profile[field]):
            invalid(f"{field} 包含该上游型号不支持的选项")
    reference_limit = profile["max_reference_images"]
    if capabilities["max_reference_images"] > reference_limit:
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
        if price.sale_unit != "image" or price.cost_unit != "image":
            invalid("图片模型计费单位必须为 image")
        variant = tuple(sorted(price.variant.items()))
        if variant in variants:
            invalid("价格组合不能重复")
        variants.add(variant)
        if price.id is not None:
            if price.id in price_ids:
                invalid("价目 ID 不能重复")
            price_ids.add(price.id)
        if set(price.variant) != set(dimensions):
            invalid("价格必须填写全部计价维度")
        for field, value in price.variant.items():
            if value not in capabilities[PARAMETERS[field]]:
                invalid("价格组合不在已配置的模型能力范围内")
    if payload.is_active:
        default_variant = tuple(sorted((field, defaults[field]) for field in dimensions))
        if default_variant not in variants:
            invalid("默认参数组合没有有效价格，请补充对应价目")


def validate_video_model(payload: ModelInput, provider: Provider) -> None:
    if provider.adapter_key != "meaicc_video":
        invalid("视频模型必须使用视频供应商")
    if payload.upstream_model_id not in {item["id"] for item in video_profiles()}:
        invalid("上游模型不在当前已核对的视频型号范围内")
    if not isinstance(payload.capabilities, VideoCapabilities):
        invalid("视频模型必须使用视频能力参数")
    caps = payload.capabilities
    if caps.min_seconds > caps.max_seconds:
        invalid("最小时长不能大于最大时长")
    for field in ("resolutions", "aspect_ratios"):
        values = getattr(caps, field)
        if (
            not values
            or any(not item.strip() for item in values)
            or len(set(values)) != len(values)
        ):
            invalid(f"{field} 必须填写不重复的有效选项")
    if set(caps.defaults) != {"seconds", "resolution", "aspect_ratio"}:
        invalid("请配置时长、分辨率和比例默认值")
    try:
        seconds = Decimal(caps.defaults["seconds"])
        if not seconds.is_finite() or not caps.min_seconds <= seconds <= caps.max_seconds:
            invalid("默认时长必须在模型时长范围内")
    except InvalidOperation:
        invalid("默认时长必须是有效数字")
    if caps.defaults["resolution"] not in caps.resolutions:
        invalid("默认分辨率必须在已配置选项内")
    if caps.defaults["aspect_ratio"] not in caps.aspect_ratios:
        invalid("默认比例必须在已配置选项内")
    if payload.pricing_dimensions:
        invalid("当前视频型号不使用计价维度，分辨率和比例配置在能力参数中")
    if len(payload.prices) != 1 or payload.prices[0].variant:
        invalid("当前视频型号需要且仅需一条默认价格")
    price = payload.prices[0]
    if price.sale_unit not in {"video", "second"} or price.cost_unit not in {"video", "second"}:
        invalid("视频计费单位必须为 video 或 second")
    if payload.is_active and (not provider.is_active or not provider.credentials_encrypted):
        invalid("上架前请启用供应商并配置密钥")


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
                "sale_unit_price": format(price.sale_unit_price, ".8f"),
                "cost_unit": price.cost_unit,
                "cost_unit_price": format(price.cost_unit_price, ".8f"),
            }
            for price in sorted(model.prices, key=lambda price: price.id)
        ],
        "token_price": (
            TokenPriceInput.model_validate(model.token_price, from_attributes=True).model_dump(
                mode="json"
            )
            if model.token_price
            else None
        ),
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
    if model is None:
        raise HTTPException(404, "模型不存在")
    if model_id and model.media_type != payload.media_type:
        invalid("模型类型不可修改，请新建模型")
    prices = {price.id: price for price in model.prices}
    if any(price.id is not None and price.id not in prices for price in payload.prices):
        invalid("价目不属于当前模型，请刷新后重试")
    if not model_id and any(price.id is not None for price in payload.prices):
        invalid("新模型不能引用已有价目")
    values = payload.model_dump(exclude={"prices", "token_price"})
    values["capabilities"] = payload.capabilities.model_dump(mode="json")
    for field, value in values.items():
        setattr(model, field, value)
    session.add(model)
    flush(session)
    if payload.token_price is not None:
        if model.token_price is None:
            model.token_price = TokenPrice(model_id=model.id)
        for field, value in payload.token_price.model_dump().items():
            setattr(model.token_price, field, value)
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
