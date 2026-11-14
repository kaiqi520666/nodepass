from decimal import Decimal
from itertools import product

from sqlalchemy import select
from test_catalog_admin import PROVIDER
from test_generations import auth_headers, prepare_user

from app.models import CreditAccount, CreditEntry, Model, Provider, Task, User
from app.providers.cangyuan import CangyuanImageAdapter
from app.services.catalog_admin import image_profiles


def test_two_models_match_parameter_prices_and_forward_upstream(client, session, monkeypatch):
    key, user = prepare_user(client, session)
    session.get(User, user["id"]).is_admin = True
    session.get(CreditAccount, user["id"]).available = Decimal("100.0000")
    session.commit()
    provider_id = client.post("/api/admin/providers", json=PROVIDER).json()["id"]
    expected_total = Decimal(0)
    submitted = []

    def capture(path, *, method, payload):
        submitted.append(payload)
        return {"id": "fake-upstream-task", "status": "queued"}

    for profile in image_profiles():
        public_id = profile["family"]
        capabilities = {k: v for k, v in profile.items() if k not in {"id", "family"}}
        capabilities["defaults"] = {
            "tier": "web",
            "quality": "medium",
            "size": "1:1",
            "background": "auto",
        }
        if profile["series"]:
            capabilities["defaults"]["series"] = "flare"
        prices = []
        variants = (
            [
                ({"tier": tier}, amount)
                for tier, amount in zip(
                    profile["tiers"], ("0.0170", "0.0550", "0.0700", "0.0800"), strict=True
                )
            ]
            if not profile["series"]
            else [
                (
                    {"series": series, "tier": tier, "quality": quality},
                    "0.0250"
                    if tier == "web"
                    else format(
                        (
                            Decimal("0.1600")
                            + Decimal(("1k", "2k", "4k").index(tier)) * Decimal("0.02")
                            + (Decimal("0.02") if series == "sunburst" else 0)
                        )
                        * (2 if quality in {"xhigh", "max"} else 1),
                        ".4f",
                    ),
                )
                for series, tier, quality in product(
                    profile["series"], profile["tiers"], profile["qualities"]
                )
            ]
        )
        for variant, amount in variants:
            prices.append(
                {
                    "variant": variant,
                    "sale_unit_price": amount,
                    "cost_unit_price": amount,
                }
            )
        payload = {
            "public_id": public_id,
            "display_name": public_id,
            "provider_id": provider_id,
            "upstream_model_id": profile["id"],
            "capabilities": capabilities,
            "pricing_dimensions": ["series", "tier", "quality"] if profile["series"] else ["tier"],
            "prices": prices,
            "is_active": True,
        }
        saved = client.post("/api/admin/models", json=payload)
        assert saved.status_code == 201, saved.text
        provider = session.get(Provider, provider_id)
        adapter = CangyuanImageAdapter(
            {"base_url": provider.base_url, "request_config": provider.request_config}, "fake-key"
        )
        monkeypatch.setattr(adapter, "_request", capture)
        for variant, amount in variants:
            response = client.post(
                "/v1/images/generations",
                headers=auth_headers(key),
                json={
                    "model": public_id,
                    "prompt": "offline parameter test",
                    **variant,
                },
            )
            assert response.status_code == 202, response.text
            task = session.scalar(select(Task).where(Task.task_id == response.json()["id"]))
            assert task.frozen_amount == Decimal(amount)
            assert task.request_params["price_variant"] == variant
            adapter.submit(task)
            assert submitted[-1]["model"] == profile["id"]
            assert all(submitted[-1][field] == value for field, value in variant.items())
            expected_total += Decimal(amount)
        # Omitting parameters uses configured defaults and still matches an exact price.
        response = client.post(
            "/v1/images/generations",
            headers=auth_headers(key),
            json={
                "model": public_id,
                "prompt": "default parameters",
            },
        )
        assert response.status_code == 202, response.text
        expected_total += Decimal("0.0250" if profile["series"] else "0.0170")
    listed = client.get("/v1/models", headers=auth_headers(key)).json()["data"]
    assert [item["id"] for item in listed] == ["gpt-image-2", "gpt-image-2.5"]
    account = session.get(CreditAccount, user["id"])
    session.refresh(account)
    assert account.frozen == expected_total
    assert account.available == Decimal("100.0000") - expected_total
    assert len(session.scalars(select(CreditEntry)).all()) == 46

    model = session.scalar(select(Model).where(Model.public_id == "gpt-image-2"))
    # A legacy empty price cannot cover a missing tier, even when no parameter was explicit.
    for price in model.prices:
        if price.variant == {"tier": "web"}:
            price.variant = {}
    session.commit()
    response = client.post(
        "/v1/images/generations",
        headers=auth_headers(key),
        json={
            "model": "gpt-image-2",
            "prompt": "missing exact price",
        },
    )
    assert response.status_code == 422
    assert session.get(CreditAccount, user["id"]).available == Decimal("100.0000") - expected_total
