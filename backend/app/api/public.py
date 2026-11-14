from fastapi import APIRouter
from sqlalchemy.orm import selectinload

from app.api.dependencies import Database
from app.core.money import money
from app.models import Model
from app.schemas import PublicModel, PublicPrice
from app.services.catalog import visible_models

router = APIRouter(prefix="/api/public", tags=["public"], include_in_schema=False)
PUBLIC_CAPABILITIES = {
    "family",
    "version",
    "min_seconds",
    "max_seconds",
    "max_reference_videos",
    "max_reference_audios",
    "supports_first_frame",
    "supports_last_frame",
    "resolutions",
    "aspect_ratios",
    "durations",
    "sizes",
    "qualities",
    "tiers",
    "series",
    "max_reference_images",
    "backgrounds",
    "output_formats",
    "supports_mask",
    "input_modalities",
}


@router.get(
    "/models", response_model=dict[str, list[PublicModel]], response_model_exclude_none=True
)
def list_models(session: Database):
    models = session.scalars(visible_models().options(selectinload(Model.prices))).all()
    return {
        "data": [
            PublicModel(
                id=model.public_id,
                name=model.display_name,
                media_type=model.media_type,
                capabilities={
                    key: value
                    for key, value in model.capabilities.items()
                    if key in PUBLIC_CAPABILITIES
                },
                prices=[
                    PublicPrice(
                        variant=price.variant,
                        unit=price.sale_unit,
                        unit_price=price.sale_unit_price,
                    )
                    for price in sorted(model.prices, key=lambda row: row.id)
                ],
                token_prices={
                    field: money(
                        getattr(model.token_price, field) * model.token_price.sale_multiplier
                    )
                    for field in ("input_price", "output_price", "cache_read_price")
                }
                if model.token_price
                else None,
                long_context_threshold=model.token_price.long_context_threshold
                if model.token_price
                else None,
                long_context_token_prices={
                    field: money(
                        getattr(model.token_price, field)
                        * model.token_price.sale_multiplier
                        * (
                            model.token_price.long_context_output_multiplier
                            if field == "output_price"
                            else model.token_price.long_context_input_multiplier
                        )
                    )
                    for field in ("input_price", "output_price", "cache_read_price")
                }
                if model.token_price
                else None,
            )
            for model in models
        ]
    }
