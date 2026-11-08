from copy import deepcopy

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import credential_cipher
from app.models import Model, Provider, SystemSetting, User
from app.services.catalog_admin import image_profiles

PROVIDER = {
    "name": "沧元测试",
    "api_key": "sk-fake-provider-key-only-for-tests",
    "is_active": True,
}


@pytest.fixture
def administrator(client, session):
    user = client.post(
        "/api/account/register",
        json={"email": "catalog-admin@example.com", "password": "test-password-only"},
    ).json()
    session.get(User, user["id"]).is_admin = True
    session.commit()
    return client


def model_payload(provider_id):
    return {
        "public_id": "site-image-test",
        "display_name": "测试图片模型",
        "provider_id": provider_id,
        "upstream_model_id": "gpt-image-2-x",
        "capabilities": {
            "tiers": ["web", "1k"],
            "qualities": ["low", "high"],
            "sizes": ["1:1", "9:16"],
            "defaults": {"tier": "web", "quality": "low", "size": "1:1"},
        },
        "pricing_dimensions": ["tier", "quality"],
        "prices": [
            {
                "variant": {},
                "sale_unit_price": "0.1000",
                "cost_unit_price": "0.01700000",
                "cost_currency": "CNY",
            }
        ],
        "is_active": True,
    }


def create_model(client):
    response = client.post("/api/admin/providers", json=PROVIDER)
    assert response.status_code == 201
    payload = model_payload(response.json()["id"])
    response = client.post("/api/admin/models", json=payload)
    assert response.status_code == 201, response.text
    return response.json(), payload


def test_gpt_image_26_web_profile_supports_size():
    profile = next(item for item in image_profiles() if item["id"] == "gpt-image-2.6")
    assert profile["sizes"] == [
        "1:1",
        "3:2",
        "16:9",
        "4:3",
        "3:4",
        "5:4",
        "4:5",
        "21:9",
        "9:21",
        "2:3",
        "9:16",
        "1:3",
        "3:1",
        "auto",
    ]


def test_gpt_image_26_web_size_is_valid(administrator):
    provider_id = administrator.post("/api/admin/providers", json=PROVIDER).json()["id"]
    payload = model_payload(provider_id)
    payload.update(
        {
            "public_id": "gpt-image-26-web-size-test",
            "upstream_model_id": "gpt-image-2.6",
            "capabilities": {
                "sizes": ["9:16"],
                "defaults": {"size": "9:16"},
            },
            "pricing_dimensions": [],
        }
    )
    response = administrator.post("/api/admin/models", json=payload)
    assert response.status_code == 201, response.text


def test_management_requires_admin_and_trusted_origin(client, session):
    paths = [
        "/api/admin/providers",
        "/api/admin/models",
        "/api/admin/image-options",
        "/api/admin/settings/oss",
    ]
    for path in paths:
        assert client.get(path).status_code == 401
    data = client.post(
        "/api/account/register",
        json={"email": "regular@example.com", "password": "test-password-only"},
    ).json()
    for path in paths:
        assert client.get(path).status_code == 403
    for path, payload in [
        ("/api/admin/providers", PROVIDER),
        ("/api/admin/models", model_payload(1)),
    ]:
        assert client.post(path, json=payload).status_code == 403
        assert client.put(f"{path}/1", json=payload).status_code == 403
    session.get(User, data["id"]).is_admin = True
    session.commit()
    assert (
        client.post(
            "/api/admin/providers", json=PROVIDER, headers={"Origin": "https://bad.invalid"}
        ).status_code
        == 403
    )


def test_provider_secret_encrypted_preserved_rotated_and_never_returned(administrator, session):
    client = administrator
    result = client.post("/api/admin/providers", json=PROVIDER)
    assert result.status_code == 201
    summary = result.json()
    assert summary["has_credentials"] is True
    provider = session.get(Provider, summary["id"])
    encrypted = provider.credentials_encrypted
    assert PROVIDER["api_key"] not in encrypted
    assert credential_cipher().decrypt(encrypted.encode()).decode() == PROVIDER["api_key"]
    for response in (result, client.get("/api/admin/providers")):
        assert PROVIDER["api_key"] not in response.text
        assert encrypted not in response.text
        assert "api_key" not in response.text
    payload = {**summary, "name": "更新名称"}
    del payload["id"], payload["has_credentials"]
    assert client.put(f"/api/admin/providers/{provider.id}", json=payload).status_code == 200
    assert provider.credentials_encrypted == encrypted
    payload["api_key"] = "sk-replacement-test-key"
    assert client.put(f"/api/admin/providers/{provider.id}", json=payload).status_code == 200
    assert (
        credential_cipher().decrypt(provider.credentials_encrypted.encode()).decode()
        == (payload["api_key"])
    )


def test_provider_rejects_missing_key_unsafe_address_and_unknown_config(administrator):
    for payload in [
        {"name": "missing-key"},
        {**PROVIDER, "base_url": "http://127.0.0.1/private"},
        {**PROVIDER, "adapter_key": "arbitrary-script"},
        {**PROVIDER, "request_config": {"script": "bad"}},
        {**PROVIDER, "api_key": "   "},
    ]:
        assert administrator.post("/api/admin/providers", json=payload).status_code == 422
    assert administrator.get("/api/admin/providers").json()["data"] == []


def test_missing_encryption_key_never_stores_plaintext(administrator, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "credentials_key", None)
    result = administrator.post("/api/admin/providers", json=PROVIDER)
    assert result.status_code == 503
    assert PROVIDER["api_key"] not in result.text
    assert session.scalar(select(Provider)) is None


def test_oss_settings_are_admin_only_and_secret_is_encrypted(administrator, session):
    client = administrator
    payload = {
        "endpoint": "oss-cn-hongkong.aliyuncs.com",
        "region": "cn-hongkong",
        "bucket": "nodepass-test",
        "access_key_id": "LTAI-test-id",
        "access_key_secret": "test-secret-only",
        "public_base_url": "https://image.nodepass.net",
        "object_prefix": "generated",
        "is_active": True,
    }
    response = client.put("/api/admin/settings/oss", json=payload)
    assert response.status_code == 200
    assert response.json()["has_credentials"] is True
    assert response.json()["public_base_url"] == payload["public_base_url"]
    setting = session.get(SystemSetting, "oss")
    assert setting is not None
    assert payload["access_key_secret"] not in setting.secret_encrypted
    assert payload["access_key_secret"] not in response.text
    assert "secret_encrypted" not in response.text
    loaded = client.get("/api/admin/settings/oss")
    assert loaded.status_code == 200
    assert loaded.json()["access_key_id"] == payload["access_key_id"]
    assert payload["access_key_secret"] not in loaded.text


def test_oss_connection_test_writes_reads_and_cleans_test_object(
    administrator, session, monkeypatch
):
    client = administrator
    payload = {
        "endpoint": "oss-cn-hongkong.aliyuncs.com",
        "region": "cn-hongkong",
        "bucket": "nodepass-test",
        "access_key_id": "LTAI-test-id",
        "access_key_secret": "test-secret-only",
        "public_base_url": "https://image.nodepass.net",
        "is_active": True,
    }
    assert client.put("/api/admin/settings/oss", json=payload).status_code == 200

    class FakeObject:
        def read(self):
            return b"NodePass OSS connection test"

    class FakeBucket:
        objects = {}

        def __init__(self, *_args, **_kwargs):
            pass

        def put_object(self, key, content):
            self.objects[key] = content

        def get_object(self, key):
            assert key in self.objects
            return FakeObject()

        def delete_object(self, key):
            self.objects.pop(key, None)

    import app.services.settings as settings_service

    monkeypatch.setattr(settings_service.oss2, "Auth", lambda *_args: object())
    monkeypatch.setattr(settings_service.oss2, "Bucket", FakeBucket)
    response = client.post("/api/admin/settings/oss/test")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert FakeBucket.objects == {}


def test_local_key_initializer_never_replaces_an_existing_key(tmp_path, monkeypatch):
    from app.cli import main

    path = tmp_path / ".env"
    content = 'export NODEPASS_CREDENTIALS_KEY = "existing-test-value"\n'
    path.write_text(content)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["nodepass", "init-credentials-key"])
    with pytest.raises(SystemExit):
        main()
    assert path.read_text() == content


def test_model_prices_publish_hide_and_atomic_update(administrator):
    client = administrator
    model, payload = create_model(client)
    listing = client.get("/api/public/models")
    assert listing.json()["data"][0]["prices"][0]["unit_price"] == "0.1000"
    for private in ["cost", "upstream_model_id", PROVIDER["api_key"], "defaults"]:
        assert private not in listing.text
    assert client.get("/api/admin/models").json()["data"][0] == model
    payload["prices"][0]["id"] = model["prices"][0]["id"]
    payload["prices"][0]["sale_unit_price"] = "0.2345"
    updated = client.put(f"/api/admin/models/{model['id']}", json=payload)
    assert updated.status_code == 200
    assert updated.json()["prices"][0]["id"] == model["prices"][0]["id"]
    assert client.get("/api/public/models").json()["data"][0]["prices"][0]["unit_price"] == (
        "0.2345"
    )
    bad = deepcopy(payload)
    bad["prices"][0]["sale_unit_price"] = "0.00001"
    assert client.put(f"/api/admin/models/{model['id']}", json=bad).status_code == 422
    assert client.get("/api/admin/models").json()["data"][0]["prices"][0]["sale_unit_price"] == (
        "0.2345"
    )
    payload["is_active"] = False
    assert client.put(f"/api/admin/models/{model['id']}", json=payload).status_code == 200
    assert client.get("/api/public/models").json()["data"] == []
    payload["is_active"] = True
    assert client.put(f"/api/admin/models/{model['id']}", json=payload).status_code == 200
    provider = client.get("/api/admin/providers").json()["data"][0]
    provider.pop("id")
    provider.pop("has_credentials")
    provider["is_active"] = False
    assert (
        client.put(f"/api/admin/providers/{model['provider_id']}", json=provider).status_code == 200
    )
    assert client.get("/api/public/models").json()["data"] == []


@pytest.mark.parametrize(
    "change",
    [
        {"prices": []},
        {"pricing_dimensions": ["size", "size"]},
        {"upstream_model_id": "gpt-image-2.6-unknown"},
        {"capabilities": {"qualities": ["low"]}},
        {"capabilities": {"max_reference_images": 16}},
    ],
)
def test_invalid_or_incomplete_models_cannot_publish(administrator, session, change):
    provider_id = administrator.post("/api/admin/providers", json=PROVIDER).json()["id"]
    payload = {**model_payload(provider_id), **change}
    assert administrator.post("/api/admin/models", json=payload).status_code == 422
    assert session.scalar(select(Model)) is None


def test_model_profile_rules_defaults_price_variants_and_cross_model_ids(administrator):
    client = administrator
    model, payload = create_model(client)
    bad = deepcopy(payload)
    bad["capabilities"]["qualities"] = ["imaginary"]
    assert client.put(f"/api/admin/models/{model['id']}", json=bad).status_code == 422
    bad = deepcopy(payload)
    bad["upstream_model_id"] = "gpt-image-2.5-x"
    assert client.put(f"/api/admin/models/{model['id']}", json=bad).status_code == 422
    bad = deepcopy(payload)
    bad["prices"] *= 2
    assert client.put(f"/api/admin/models/{model['id']}", json=bad).status_code == 422
    bad = deepcopy(payload)
    bad["prices"][0]["variant"] = {"tier": "web"}
    assert client.put(f"/api/admin/models/{model['id']}", json=bad).status_code == 422
    bad["prices"][0]["variant"] = {"tier": "1k", "quality": "low"}
    assert client.put(f"/api/admin/models/{model['id']}", json=bad).status_code == 422
    bad["prices"][0]["variant"] = {"tier": "web", "quality": "low"}
    assert client.put(f"/api/admin/models/{model['id']}", json=bad).status_code == 200
    duplicate = client.post("/api/admin/models", json=payload)
    assert duplicate.status_code == 409
    other = deepcopy(payload)
    other["public_id"] = "another-model"
    other = client.post("/api/admin/models", json=other).json()
    payload["prices"][0]["id"] = other["prices"][0]["id"]
    assert client.put(f"/api/admin/models/{model['id']}", json=payload).status_code == 422


def test_fixed_pixel_limits_and_variant_swap_preserve_price_ids(administrator):
    client = administrator
    model, payload = create_model(client)
    payload["upstream_model_id"] = "gpt-image-2.6-flare-4k"
    payload["capabilities"] = {
        "qualities": ["low", "high"],
        "sizes": ["2880x2880"],
        "defaults": {"quality": "low", "size": "2880x2880"},
    }
    payload["pricing_dimensions"] = ["quality"]
    price = payload["prices"][0]
    payload["prices"] = [{**price, "variant": {"quality": quality}} for quality in ["low", "high"]]
    saved = client.put(f"/api/admin/models/{model['id']}", json=payload)
    assert saved.status_code == 200, saved.text
    payload["prices"] = saved.json()["prices"]
    payload["prices"][0]["variant"], payload["prices"][1]["variant"] = (
        payload["prices"][1]["variant"],
        payload["prices"][0]["variant"],
    )
    assert client.put(f"/api/admin/models/{model['id']}", json=payload).status_code == 200
    payload["capabilities"]["sizes"] = ["3840x2160"]
    payload["capabilities"]["defaults"]["size"] = "3840x2160"
    assert client.put(f"/api/admin/models/{model['id']}", json=payload).status_code == 200
    payload["capabilities"]["sizes"] = ["3841x2160"]
    assert client.put(f"/api/admin/models/{model['id']}", json=payload).status_code == 422


@pytest.mark.parametrize(
    "upstream_id",
    [
        "gpt-image-2.5-flare",
        "gpt-image-2.5-sunburst",
        "gpt-image-2.6-flare",
        "gpt-image-2.6-sunburst",
    ],
)
def test_web_reference_limit_is_configurable_and_published(administrator, upstream_id):
    client = administrator
    options = client.get("/api/admin/image-options").json()["data"]
    assert (
        next(profile for profile in options if profile["id"] == upstream_id)["max_reference_images"]
        is None
    )
    provider_id = client.post("/api/admin/providers", json=PROVIDER).json()["id"]
    payload = {
        **model_payload(provider_id),
        "upstream_model_id": upstream_id,
        "capabilities": {"max_reference_images": 16},
        "pricing_dimensions": [],
    }
    saved = client.post("/api/admin/models", json=payload)
    assert saved.status_code == 201, saved.text
    model_id = saved.json()["id"]
    assert saved.json()["capabilities"]["max_reference_images"] == 16
    assert (
        client.get("/api/public/models").json()["data"][0]["capabilities"]["max_reference_images"]
        == 16
    )
    payload["capabilities"]["max_reference_images"] = 8
    assert client.put(f"/api/admin/models/{model_id}", json=payload).status_code == 200
    for invalid_limit in (-1, 17):
        payload["capabilities"]["max_reference_images"] = invalid_limit
        assert client.put(f"/api/admin/models/{model_id}", json=payload).status_code == 422
    assert (
        client.get("/api/public/models").json()["data"][0]["capabilities"]["max_reference_images"]
        == 8
    )


def test_selected_image_models_allow_database_configured_mask(administrator):
    client = administrator
    provider_id = client.post("/api/admin/providers", json=PROVIDER).json()["id"]
    upstream_ids = [f"gpt-image-2{suffix}" for suffix in ("", "-1k", "-2k", "-4k")] + [
        f"gpt-image-{version}-{branch}{suffix}"
        for version in ("2.5", "2.6")
        for branch in ("flare", "sunburst")
        for suffix in ("", "-1k", "-2k", "-4k")
    ]
    assert len(upstream_ids) == 20
    for upstream_id in upstream_ids:
        payload = {
            **model_payload(provider_id),
            "public_id": upstream_id,
            "upstream_model_id": upstream_id,
            "capabilities": {"supports_mask": True},
            "pricing_dimensions": [],
        }
        saved = client.post("/api/admin/models", json=payload)
        assert saved.status_code == 201, saved.text
        assert saved.json()["capabilities"]["supports_mask"] is True
        assert (
            client.put(f"/api/admin/models/{saved.json()['id']}", json=payload).status_code == 200
        )
    published = client.get("/api/public/models").json()["data"]
    assert len(published) == 20
    assert all(model["capabilities"]["supports_mask"] is True for model in published)
