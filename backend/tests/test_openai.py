import pytest
from fastapi.testclient import TestClient
from openai import AuthenticationError, OpenAI
from sqlalchemy.exc import SQLAlchemyError
from test_accounts import CREDENTIALS, register
from test_catalog import add_model

from app.api.dependencies import api_key_user
from app.core.database import get_session
from app.core.security import SESSION_COOKIE, digest_api_key
from app.models import ApiKey, User


def create_key(client, name="Local development"):
    response = client.post("/api/account/keys", json={"name": name})
    assert response.status_code == 201
    return response


def auth_headers(key):
    return {"Authorization": f"Bearer {key}"}


def test_key_creation_stores_only_digest_and_returns_secret_once(client, session):
    user = register(client).json()
    assert client.get("/api/account/keys").json() == {"data": []}
    response = create_key(client)
    created = response.json()
    assert created["key"].startswith("sk-nodepass-")
    assert len(created["key"]) == len("sk-nodepass-") + 43
    stored = session.get(ApiKey, created["id"])
    assert stored.user_id == user["id"]
    assert stored.key_digest == digest_api_key(created["key"])
    assert created["key_prefix"] == created["key"][:19]
    assert created["key"] not in str(stored.__dict__)
    assert "key_digest" not in response.text
    assert response.headers["cache-control"] == "no-store"
    listing = client.get("/api/account/keys")
    assert "key_digest" not in listing.text
    assert created["key"] not in listing.text
    assert "key" not in listing.json()["data"][0]
    assert create_key(client).json()["key"] != created["key"]


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
def test_key_name_validation(client, name):
    register(client)
    assert client.post("/api/account/keys", json={"name": name}).status_code == 422


def test_key_cannot_select_another_owner_or_set_privileges(client, session):
    register(client)
    assert (
        client.post("/api/account/keys", json={"name": "unsafe", "user_id": 999}).status_code == 422
    )
    first = create_key(client).json()
    client.post("/api/account/logout")
    assert client.get("/api/account/keys").status_code == 401
    assert client.post("/api/account/keys", json={"name": "anonymous"}).status_code == 401
    assert client.post(f"/api/account/keys/{first['id']}/revoke").status_code == 401
    client.post("/api/account/register", json={**CREDENTIALS, "email": "other@example.com"})
    assert client.get("/api/account/keys").json() == {"data": []}
    assert client.post(f"/api/account/keys/{first['id']}/revoke").status_code == 404
    assert session.get(ApiKey, first["id"]).is_active is True


def test_key_creation_and_revocation_require_trusted_origin(client, session):
    register(client)
    created = create_key(client).json()
    for origin in ("", "https://untrusted.example"):
        assert (
            client.post(
                "/api/account/keys", json={"name": "csrf"}, headers={"Origin": origin}
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/account/keys/{created['id']}/revoke", headers={"Origin": origin}
            ).status_code
            == 403
        )
    assert session.get(ApiKey, created["id"]).is_active is True


@pytest.mark.parametrize(
    "authorization",
    ["", "Bearer", "Basic abc", "Bearer incorrect", "Bearer sk-nodepass-" + "A" * 43],
)
def test_models_require_real_bearer_key_even_when_logged_in(client, authorization):
    register(client)
    response = client.get("/v1/models", headers={"Authorization": authorization})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "error": {
            "message": "Invalid API key.",
            "type": "invalid_request_error",
            "param": None,
            "code": "invalid_api_key",
        }
    }
    if authorization:
        assert authorization not in response.text


def test_web_session_is_not_api_key_and_key_cannot_manage_account(client):
    register(client)
    created = create_key(client).json()
    web_token = client.cookies.get(SESSION_COOKIE)
    assert client.get("/v1/models", headers=auth_headers(web_token)).status_code == 401
    client.cookies.clear()
    assert client.get("/api/account/me", headers=auth_headers(created["key"])).status_code == 401
    assert client.get("/api/account/keys", headers=auth_headers(created["key"])).status_code == 401
    response = client.get("/v1/models", headers={**auth_headers(created["key"]), "Origin": ""})
    assert response.status_code == 200
    assert response.json() == {"object": "list", "data": []}


def test_model_shape_privacy_and_last_used_timestamp(client, session):
    register(client)
    created = create_key(client).json()
    _, model, _ = add_model(session)
    response = client.get("/v1/models", headers=auth_headers(created["key"]))
    assert response.json() == {
        "object": "list",
        "data": [
            {
                "id": "test-public-model",
                "object": "model",
                "created": int(model.created_at.timestamp()),
                "owned_by": "nodepass",
            }
        ],
    }
    assert response.headers["cache-control"] == "no-store"
    for private in ("prices", "cost", "upstream", "supplier", "private_setting", "capabilities"):
        assert private not in response.text
    session.expire_all()
    assert session.get(ApiKey, created["id"]).last_used_at is not None


@pytest.mark.parametrize("hidden", ["provider", "model", "price"])
def test_both_catalogs_use_same_visibility_rules(client, session, hidden):
    register(client)
    created = create_key(client).json()
    provider, model, price = add_model(session)
    if hidden == "provider":
        provider.is_active = False
    elif hidden == "model":
        model.is_active = False
    else:
        session.delete(price)
    session.commit()
    assert client.get("/api/public/models").json() == {"data": []}
    assert client.get("/v1/models", headers=auth_headers(created["key"])).json() == {
        "object": "list",
        "data": [],
    }


def test_revoking_key_is_idempotent_preserves_history_and_rejects_next_call(client, session):
    register(client)
    created = create_key(client).json()
    other = create_key(client).json()
    assert client.get("/v1/models", headers=auth_headers(created["key"])).status_code == 200
    for _ in range(2):
        assert client.post(f"/api/account/keys/{created['id']}/revoke").status_code == 204
    assert session.get(ApiKey, created["id"]).is_active is False
    assert client.get("/v1/models", headers=auth_headers(created["key"])).status_code == 401
    assert client.get("/v1/models", headers=auth_headers(other["key"])).status_code == 200
    assert len(client.get("/api/account/keys").json()["data"]) == 2


def test_disabled_user_key_stops_working_without_manual_key_revocation(client, session):
    user = register(client).json()
    created = create_key(client).json()
    session.get(User, user["id"]).is_active = False
    session.commit()
    assert client.get("/v1/models", headers=auth_headers(created["key"])).status_code == 401
    assert client.get("/api/account/keys").status_code == 401


def test_official_openai_sdk_reads_models_and_authentication_error(client, session):
    register(client)
    created = create_key(client).json()
    add_model(session)
    sdk = OpenAI(
        api_key=created["key"],
        base_url="http://testserver/v1",
        http_client=client,
        max_retries=0,
    )
    result = sdk.models.list()
    assert result.object == "list"
    assert len(result.data) == 1
    assert result.data[0].id == "test-public-model"
    assert result.data[0].object == "model"
    assert isinstance(result.data[0].created, int)
    assert result.data[0].owned_by == "nodepass"
    client.post(f"/api/account/keys/{created['id']}/revoke")
    with pytest.raises(AuthenticationError) as error:
        sdk.models.list()
    assert error.value.code == "invalid_api_key"


def test_v1_routing_errors_keep_openai_shape(client):
    for response in (
        client.get("/v1/not-implemented"),
        client.post("/v1/models"),
    ):
        assert response.status_code in (404, 405)
        assert set(response.json()) == {"error"}
        assert set(response.json()["error"]) == {"message", "type", "param", "code"}
        assert "detail" not in response.json()


def test_openapi_exposes_only_supported_developer_endpoint(client):
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/v1/models",
        "/v1/images/generations",
        "/v1/images/generations/{task_id}",
    }
    assert schema["paths"]["/v1/models"]["get"]["security"] == [{"HTTPBearer": []}]
    assert schema["paths"]["/v1/images/generations"]["post"]["security"] == [{"HTTPBearer": []}]
    assert schema["paths"]["/v1/images/generations/{task_id}"]["get"]["security"] == [
        {"HTTPBearer": []}
    ]


def test_database_error_does_not_expose_credentials_or_sql(client):
    def broken_session():
        raise SQLAlchemyError("private SQL or API key")

    client.app.dependency_overrides[get_session] = broken_session
    try:
        response = client.get("/v1/models")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_unavailable"
        assert "private SQL" not in response.text
    finally:
        client.app.dependency_overrides.pop(get_session)


def test_unexpected_v1_error_is_sanitized(client):
    def broken_auth():
        raise RuntimeError("private exception or secret")

    client.app.dependency_overrides[api_key_user] = broken_auth
    try:
        with TestClient(client.app, raise_server_exceptions=False) as failing_client:
            response = failing_client.get("/v1/models")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "private exception" not in response.text
    finally:
        client.app.dependency_overrides.pop(api_key_user)
