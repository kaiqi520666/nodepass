from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Model, ModelPrice, Provider


def add_model(session):
    provider = Provider(
        name="test-provider",
        adapter_key="test",
        base_url="https://supplier.invalid",
        credentials_encrypted="test-ciphertext-not-a-real-key",
    )
    session.add(provider)
    session.flush()
    model = Model(
        public_id="test-public-model",
        display_name="Test model",
        media_type="image",
        provider_id=provider.id,
        upstream_model_id="private-upstream-model",
        capabilities={"sizes": ["1024x1024"], "private_setting": "must-not-be-public"},
        is_active=True,
    )
    session.add(model)
    session.flush()
    price = ModelPrice(
        model_id=model.id,
        variant={},
        sale_unit="image",
        sale_unit_price=Decimal("1.2300"),
        cost_unit="image",
        cost_unit_price=Decimal("0.01700000"),
        cost_currency="CNY",
    )
    session.add(price)
    session.commit()
    return provider, model, price


def test_catalog_empty_then_returns_only_public_fields(client, session):
    assert client.get("/api/public/models").json() == {"data": []}
    add_model(session)
    response = client.get("/api/public/models")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {
                "id": "test-public-model",
                "name": "Test model",
                "media_type": "image",
                "capabilities": {"sizes": ["1024x1024"]},
                "prices": [{"variant": {}, "unit": "image", "unit_price": "1.2300"}],
            }
        ]
    }
    for private in ("cost", "supplier.invalid", "ciphertext", "upstream", "private_setting"):
        assert private not in response.text


@pytest.mark.parametrize("hidden", ["provider", "model", "price"])
def test_inactive_or_unpriced_models_are_not_public(client, session, hidden):
    provider, model, price = add_model(session)
    if hidden == "provider":
        provider.is_active = False
    elif hidden == "model":
        model.is_active = False
    else:
        session.delete(price)
    session.commit()
    assert client.get("/api/public/models").json() == {"data": []}


def test_json_price_uniqueness_ignores_object_key_order(client, session):
    _, model, price = add_model(session)
    price.variant = {"tier": "web", "quality": "low"}
    session.commit()
    session.add(
        ModelPrice(
            model_id=model.id,
            variant={"quality": "low", "tier": "web"},
            sale_unit="image",
            sale_unit_price=Decimal("2.0000"),
            cost_unit="image",
            cost_unit_price=Decimal("0.01000000"),
            cost_currency="CNY",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_health_checks_use_database(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok", "database": "connected"}
