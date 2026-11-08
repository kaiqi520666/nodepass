from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models import ApiKey, CreditEntry, User


def create_account(client, email):
    response = client.post(
        "/api/account/register",
        json={"email": email, "password": "test-password-only"},
    )
    assert response.status_code == 201
    return response.json()


def login(client, email):
    response = client.post(
        "/api/account/login",
        json={"email": email, "password": "test-password-only"},
    )
    assert response.status_code == 200


def test_admin_can_adjust_user_credits_and_records_ledger(client, session):
    target = create_account(client, "target@example.com")
    client.post("/api/account/logout")
    admin = create_account(client, "admin@example.com")
    session.get(User, admin["id"]).is_admin = True
    session.commit()
    response = client.post(
        f"/api/admin/users/{target['id']}/credits",
        json={"direction": "increase", "amount": "1.23456", "reason": "测试充值"},
    )
    assert response.status_code == 200
    assert response.json()["account"]["available"] == "1.2346"
    entry = session.scalar(select(CreditEntry).where(CreditEntry.entry_type == "admin_credit"))
    assert entry is not None
    assert entry.amount == Decimal("1.2346")

    response = client.post(
        f"/api/admin/users/{target['id']}/credits",
        json={"direction": "decrease", "amount": "0.2346", "reason": "测试扣除"},
    )
    assert response.status_code == 200
    assert response.json()["account"]["available"] == "1.0000"
    assert (
        client.post(
            f"/api/admin/users/{target['id']}/credits",
            json={"direction": "decrease", "amount": "2", "reason": "余额不足"},
        ).status_code
        == 409
    )


def test_admin_can_update_user_password(client, session):
    target = create_account(client, "password-target@example.com")
    client.post("/api/account/logout")
    admin = create_account(client, "password-admin@example.com")
    session.get(User, admin["id"]).is_admin = True
    session.commit()

    response = client.post(
        f"/api/admin/users/{target['id']}/password",
        json={"password": "updated-password"},
    )
    assert response.status_code == 200
    client.post("/api/account/logout")
    assert (
        client.post(
            "/api/account/login",
            json={"email": target["email"], "password": "updated-password"},
        ).status_code
        == 200
    )


def test_api_key_can_be_viewed_updated_deleted_and_expired(client, session):
    account = create_account(client, "keys@example.com")
    expires_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    created = client.post(
        "/api/account/keys",
        json={"name": "可管理", "expires_at": expires_at},
    ).json()
    assert created["expires_at"] is not None
    assert client.get(f"/api/account/keys/{created['id']}/secret").json() == {"key": created["key"]}
    updated = client.put(
        f"/api/account/keys/{created['id']}",
        json={"name": "已更新", "expires_at": None},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "已更新"
    assert updated.json()["expires_at"] is None
    assert client.delete(f"/api/account/keys/{created['id']}").status_code == 204
    assert session.get(ApiKey, created["id"]) is None

    client.post("/api/account/logout")
    login(client, account["email"])
    expired = client.post(
        "/api/account/keys",
        json={
            "name": "已过期",
            "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        },
    ).json()
    assert (
        client.get("/v1/models", headers={"Authorization": f"Bearer {expired['key']}"}).status_code
        == 401
    )
