from datetime import UTC, datetime, timedelta
from decimal import Decimal

import jwt
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DataError, IntegrityError

from app.core.config import get_settings
from app.core.security import SESSION_COOKIE, password_hash
from app.models import CreditAccount, User

CREDENTIALS = {"email": "user@example.com", "password": "test-password-only"}


def register(client):
    response = client.post("/api/account/register", json=CREDENTIALS)
    assert response.status_code == 201
    return response


def test_registration_login_logout_and_decimal_balance(client, session):
    response = register(client)
    data = response.json()
    assert data["account"] == {"available": "0.00000000", "frozen": "0.00000000"}
    assert data["is_admin"] is False
    assert not {"password_hash", "password", "session_secret"} & data.keys()
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    user = session.scalar(select(User))
    assert user.password_hash != CREDENTIALS["password"]
    assert password_hash.verify(CREDENTIALS["password"], user.password_hash)
    assert client.get("/api/account/me").json()["id"] == user.id
    assert client.post("/api/account/logout").status_code == 204
    assert client.get("/api/account/me").status_code == 401
    assert (
        client.post(
            "/api/account/login",
            json={**CREDENTIALS, "email": "USER@example.com"},
        ).status_code
        == 200
    )


def test_duplicate_email_cannot_create_second_account(client, session):
    register(client)
    response = client.post(
        "/api/account/register", json={**CREDENTIALS, "email": "USER@example.com"}
    )
    assert response.status_code == 409
    assert session.scalar(select(func.count()).select_from(User)) == 1
    assert session.scalar(select(func.count()).select_from(CreditAccount)) == 1


def test_password_and_privilege_fields_are_not_echoed(client):
    response = client.post("/api/account/register", json={**CREDENTIALS, "is_admin": True})
    assert response.status_code == 422
    assert CREDENTIALS["password"] not in response.text
    assert "input" not in response.text
    assert client.get("/api/account/me").status_code == 401


@pytest.mark.parametrize("password", ["abc12?", "x" * 129])
def test_password_length_validation(client, password):
    response = client.post("/api/account/register", json={**CREDENTIALS, "password": password})
    assert response.status_code == 422
    assert password not in response.text


def test_unsafe_web_requests_require_trusted_origin(client):
    for headers in ({"Origin": "https://untrusted.example"}, {"Origin": ""}):
        assert (
            client.post("/api/account/register", json=CREDENTIALS, headers=headers).status_code
            == 403
        )
    assert client.get("/api/public/models", headers={"Origin": ""}).status_code == 200


def test_wrong_password_unknown_email_and_disabled_account(client, session):
    register(client)
    client.post("/api/account/logout")
    for credentials in (
        {**CREDENTIALS, "password": "wrong-password"},
        {**CREDENTIALS, "email": "missing@example.com"},
    ):
        response = client.post("/api/account/login", json=credentials)
        assert response.status_code == 401
        assert response.json()["detail"] == "邮箱或密码不正确"
    user = session.scalar(select(User))
    user.is_active = False
    session.commit()
    assert client.post("/api/account/login", json=CREDENTIALS).status_code == 401


def test_backend_enforces_admin_and_refreshes_role_from_database(client, session):
    assert client.get("/api/admin/users").status_code == 401
    data = register(client).json()
    assert client.get("/api/admin/users").status_code == 403
    user = session.get(User, data["id"])
    user.is_admin = True
    session.commit()
    response = client.get("/api/admin/users")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["data"][0]["id"] == data["id"]
    user.is_admin = False
    session.commit()
    assert client.get("/api/admin/users").status_code == 403
    user.is_active = False
    session.commit()
    assert client.get("/api/account/me").status_code == 401


def test_forged_and_expired_sessions_are_rejected(client):
    data = register(client).json()
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": str(data["id"]),
            "aud": "nodepass-web",
            "iss": "nodepass",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        get_settings().session_secret.get_secret_value(),
        algorithm="HS256",
    )
    for token in ("forged", expired):
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, token, path="/api")
        assert client.get("/api/account/me").status_code == 401


@pytest.mark.parametrize(
    ("invalid", "error_type"),
    [("NaN", IntegrityError), ("Infinity", DataError), ("-Infinity", DataError)],
)
def test_database_rejects_invalid_balances(client, session, invalid, error_type):
    data = register(client).json()
    account = session.get(CreditAccount, data["id"])
    account.available = Decimal(invalid)
    with pytest.raises(error_type):
        session.commit()
    session.rollback()
    assert session.get(CreditAccount, data["id"]).available == Decimal("0.0000")


def test_me_never_selects_another_account_from_query(client):
    data = register(client).json()
    assert client.get("/api/account/me?user_id=99999").json()["id"] == data["id"]
    assert "no-store" in client.get("/api/account/me").headers["cache-control"]


def test_management_routes_are_not_published_in_openapi(client):
    schema = client.get("/openapi.json").json()
    assert not any(path.startswith("/api/admin") for path in schema["paths"])
