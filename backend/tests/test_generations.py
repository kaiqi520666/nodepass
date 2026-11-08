from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from test_accounts import register
from test_catalog import add_model

from app.models import CreditAccount, CreditEntry, Task


def create_key(client):
    response = client.post("/api/account/keys", json={"name": "generation test"})
    assert response.status_code == 201
    return response.json()["key"]


def auth_headers(key):
    return {"Authorization": f"Bearer {key}"}


def prepare_user(client, session):
    user = register(client).json()
    account = session.get(CreditAccount, user["id"])
    account.available = Decimal("2.0000")
    session.commit()
    return create_key(client), user


def test_generation_validates_n_and_does_not_freeze_on_invalid_request(client, session):
    key, user = prepare_user(client, session)
    add_model(session)
    response = client.post(
        "/v1/images/generations",
        headers=auth_headers(key),
        json={"model": "test-public-model", "prompt": "a test image", "n": 2},
    )
    assert response.status_code == 422
    account = session.get(CreditAccount, user["id"])
    assert account.available == Decimal("2.0000")
    assert session.scalar(select(Task)) is None
    assert session.scalar(select(CreditEntry)) is None


def test_generation_matches_price_and_freezes_points_once(client, session):
    key, user = prepare_user(client, session)
    add_model(session)
    response = client.post(
        "/v1/images/generations",
        headers=auth_headers(key),
        json={"model": "test-public-model", "prompt": "a test image"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["object"] == "image.generation"
    assert body["status"] == "queued"
    assert body["model"] == "test-public-model"
    task = session.scalar(select(Task))
    assert task.task_id is not None
    assert task.billing_status == "held"
    assert task.frozen_amount == Decimal("1.2300")
    account = session.get(CreditAccount, user["id"])
    assert account.available == Decimal("0.7700")
    assert account.frozen == Decimal("1.2300")
    entry = session.scalar(select(CreditEntry))
    assert entry.entry_type == "freeze"
    assert entry.available_delta == Decimal("-1.2300")
    assert entry.frozen_delta == Decimal("1.2300")
    status_response = client.get(
        f"/v1/images/generations/{body['id']}",
        headers=auth_headers(key),
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "queued"
    assert status_response.json()["data"] == []


def test_generation_rejects_unpriced_variant_and_insufficient_balance(client, session):
    key, user = prepare_user(client, session)
    _, model, _ = add_model(session)
    model.capabilities = {"qualities": ["low", "high"], "defaults": {"quality": "low"}}
    model.pricing_dimensions = ["quality"]
    session.commit()
    response = client.post(
        "/v1/images/generations",
        headers=auth_headers(key),
        json={"model": "test-public-model", "prompt": "a test image", "quality": "high"},
    )
    assert response.status_code == 422
    account = session.get(CreditAccount, user["id"])
    assert account.available == Decimal("2.0000")
    account.available = Decimal("0.0001")
    session.commit()
    response = client.post(
        "/v1/images/generations",
        headers=auth_headers(key),
        json={"model": "test-public-model", "prompt": "a test image"},
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "insufficient_quota"
    assert session.scalar(select(Task)) is None


def test_generation_requires_api_key_even_with_web_session(client, session):
    register(client)
    add_model(session)
    response = client.post(
        "/v1/images/generations",
        json={"model": "test-public-model", "prompt": "a test image"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_task_log_exposes_details_without_user_delete(client, session):
    key, user = prepare_user(client, session)
    add_model(session)
    response = client.post(
        "/v1/images/generations",
        headers=auth_headers(key),
        json={"model": "test-public-model", "prompt": "a test image"},
    )
    task = session.scalar(select(Task))
    task.status = "succeeded"
    task.billing_status = "settled"
    task.completed_at = datetime.now(UTC)
    session.commit()

    listed = client.get("/api/account/tasks")
    assert listed.status_code == 200
    item = listed.json()["data"][0]
    assert item["id"] == response.json()["id"]
    assert item["media_type"] == "image"
    assert item["model_name"] == "Test model"
    assert item["consumed_amount"] == "1.2300"
    assert item["duration_ms"] >= 0
    assert item["request_params"]["prompt"] == "a test image"

    assert client.delete(f"/api/account/tasks/{item['id']}").status_code == 405
    assert session.get(Task, task.id) is not None
    assert session.scalar(select(CreditEntry).where(CreditEntry.task_id == task.id)) is not None
