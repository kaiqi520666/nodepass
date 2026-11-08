from sqlalchemy import select

from app.models import Model, Provider


def visible_models():
    return (
        select(Model)
        .join(Provider, Model.provider_id == Provider.id)
        .where(Model.is_active, Provider.is_active, Model.prices.any())
        .order_by(Model.public_id)
    )
