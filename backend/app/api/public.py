from fastapi import APIRouter
from sqlalchemy.orm import selectinload

from app.api.dependencies import Database
from app.models import Model
from app.schemas import PublicModel, PublicPrice
from app.services.catalog import visible_models

router = APIRouter(prefix="/api/public", tags=["public"], include_in_schema=False)
PUBLIC_CAPABILITIES = {
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
}


@router.get("/models", response_model=dict[str, list[PublicModel]])
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
            )
            for model in models
        ]
    }
