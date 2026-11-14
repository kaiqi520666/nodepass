import json
from collections import deque
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_catalog import add_model
from test_generations import auth_headers, create_key, prepare_user

from app.core.security import credential_cipher
from app.models import CreditAccount, CreditEntry, Task
from app.providers import CangyuanImageAdapter, ProviderError
from app.services import task_execution

EXAMPLE = json.loads(
    (
        Path(__file__).resolve().parents[2] / "frontend/src/views/docs/image-edit.example.json"
    ).read_text()
)


@pytest.fixture
def edits(client, session, monkeypatch):
    key, user = prepare_user(client, session)
    provider, model, price = add_model(session)
    provider.adapter_key = "cangyuan_image"
    provider.credentials_encrypted = credential_cipher().encrypt(b"fake-key").decode()
    provider.request_config = {
        "timeout_seconds": 30,
        "poll_interval_seconds": 90,
        "task_timeout_seconds": 1800,
    }
    model.public_id = "gpt-image-2"
    model.upstream_model_id = "gpt-image-2-x"
    model.capabilities = {
        "tiers": ["web", "1k"],
        "sizes": ["16:9", "1:1"],
        "defaults": {"tier": "web", "size": "16:9"},
        "max_reference_images": 9,
        "supports_mask": True,
    }
    model.pricing_dimensions = ["tier"]
    price.variant = {"tier": "web"}
    session.commit()
    events, calls, uploads = deque(), [], []

    def request(adapter, path, *, method="GET", payload=None):
        calls.append((path, method, payload, adapter.timeout))
        event = events.popleft()
        if isinstance(event, Exception):
            raise event
        return event

    def upload(_session, task_id, position, content, content_type):
        uploads.append((task_id, position, content, content_type))
        return {
            "region": "test",
            "bucket": "test",
            "object_key": f"{task_id}/{position}.png",
            "public_url": f"https://media.example.com/{task_id}/{position}.png",
            "content_type": content_type,
            "byte_size": len(content),
        }

    monkeypatch.setattr(CangyuanImageAdapter, "_request", request)
    monkeypatch.setattr(task_execution, "decode_output", lambda _: (b"image", "image/png"))
    monkeypatch.setattr(task_execution, "upload_result", upload)
    return key, user, provider, model, events, calls, uploads


def submit(client, key, selected_model, **params):
    return client.post(
        "/v1/images/edits",
        headers=auth_headers(key),
        json={**deepcopy(EXAMPLE), "model": selected_model.public_id, **params},
    )


@pytest.mark.parametrize("family", ["gpt-image-2", "gpt-image-2.5"])
@pytest.mark.parametrize("mask", [None, {"image_url": "https://example.com/mask.png"}])
def test_edit_mapping_restart_transfer_retry_and_single_settlement(
    client, session, edits, monkeypatch, family, mask
):
    key, user, provider, model, events, calls, uploads = edits
    model.public_id = family
    model.upstream_model_id = f"{family}-x"
    session.commit()
    response = submit(client, key, model, mask=mask)
    assert response.status_code == 202, response.text
    body = response.json()
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/v1/images/edits"]["post"]["responses"]["202"]
    assert set(body) == set(schema["components"]["schemas"]["QueuedImageGeneration"]["properties"])
    assert body["object"] == "image.generation" and body["data"] == []
    task = session.scalar(select(Task).where(Task.task_id == body["id"]))
    path = f"/v1/images/generations/{task.task_id}"
    assert task.frozen_amount == Decimal("1.23000000")
    assert task.request_params["images"] == EXAMPLE["images"]
    assert task.request_params["price_variant"] == {"tier": "web"}
    events.extend(
        [
            {"id": "edit-1", "status": "queued"},
            {
                "id": "edit-1",
                "status": "completed",
                "data": [{"url": "https://example.com/out.png"}],
            },
        ]
    )
    task_execution.process_task(session, task)
    assert task.status == "pending"
    expected = {
        "model": f"{family}-x",
        "prompt": EXAMPLE["prompt"],
        "n": 1,
        "async": True,
        "tier": "web",
        "size": "16:9",
        "images": [item["image_url"] for item in EXAMPLE["images"]],
    }
    if mask:
        expected["mask"] = mask["image_url"]
    assert calls[0] == ("/v1/images/edits", "POST", expected, 30)
    # In-flight edits retain their operation, price and timeout across sessions/config changes.
    provider.request_config = {**provider.request_config, "timeout_seconds": 10}
    model.prices[0].sale_unit_price = Decimal("99")
    session.commit()

    def failed_upload(*_args, **_kwargs):
        raise ProviderError("temporary storage failure")

    with monkeypatch.context() as patch:
        patch.setattr(task_execution, "upload_result", failed_upload)
        with Session(session.bind) as restarted:
            task_execution.process_task(restarted, restarted.get(Task, task.id))
    session.refresh(task)
    assert calls[1] == ("/v1/images/edits/edit-1", "GET", None, 30)
    assert task.status == "transferring" and task.billing_status == "held"
    assert client.get(path, headers=auth_headers(key)).json()["data"] == []
    assert len(session.scalars(select(CreditEntry)).all()) == 1
    task_execution.process_task(session, task)
    for _ in range(2):
        task_execution.process_task(session, task)
        result = client.get(path, headers=auth_headers(key)).json()
        assert result["status"] == "succeeded" and result["completed"] is not None
        assert result["data"] == [{"url": f"https://media.example.com/{task.task_id}/0.png"}]
        assert result["error"] is None
    account = session.get(CreditAccount, user["id"])
    session.refresh(account)
    assert account.available == Decimal("0.77000000") and account.frozen == 0
    assert len(calls) == 2 and len(uploads) == 1
    assert [
        row.entry_type for row in session.scalars(select(CreditEntry).order_by(CreditEntry.id))
    ] == [
        "freeze",
        "settle",
    ]
    logged = client.get("/api/account/tasks").json()["data"][0]
    assert logged["media_type"] == "image"
    assert logged["request_params"]["images"] == EXAMPLE["images"]
    assert logged["consumed_amount"] == "1.23000000"


@pytest.mark.parametrize(
    ("params", "capabilities"),
    [
        ({"images": []}, {}),
        ({"images": [{"image_url": "https://example.com/a.png"}] * 10}, {}),
        ({"images": [{"image_url": "http://example.com/a.png"}]}, {}),
        ({"images": [{"image_url": "https://127.0.0.1/a.png"}]}, {}),
        ({"images": [{"image_url": "data:image/png;base64,aW1hZ2U="}]}, {}),
        ({"images": [{"file_id": "file-1"}]}, {}),
        ({"image": "https://example.com/a.png"}, {}),
        ({"mask": {"image_url": "https://localhost/mask.png"}}, {}),
        ({"mask": {"image_url": "https://example.com/mask.png"}}, {"supports_mask": False}),
        ({}, {"max_reference_images": 0}),
        ({"n": 2}, {}),
        ({"response_format": "b64_json"}, {}),
        ({"tier": "1k"}, {}),
        ({"size": "unsupported"}, {}),
    ],
)
def test_invalid_edits_never_create_task_or_freeze(client, session, edits, params, capabilities):
    key, user, _, model, _, calls, _ = edits
    model.capabilities = {**model.capabilities, **capabilities}
    session.commit()
    response = submit(client, key, model, **params)
    assert response.status_code == 422, response.text
    assert session.scalar(select(Task)) is None
    assert session.scalar(select(CreditEntry)) is None
    account = session.get(CreditAccount, user["id"])
    assert account.available == Decimal("2.00000000") and account.frozen == 0
    assert calls == []


@pytest.mark.parametrize("outcome", ["failed", "rejected", "unknown", "late_success"])
def test_edit_failure_unknown_and_timeout_billing(client, session, edits, outcome):
    key, user, _, model, events, calls, _ = edits
    response = submit(client, key, model)
    assert response.status_code == 202
    task = session.scalar(select(Task))
    if outcome == "rejected":
        events.append(ProviderError("rejected", explicit_failure=True))
    elif outcome == "unknown":
        events.append(ProviderError("request interrupted"))
    else:
        events.extend(
            [
                {"id": "edit-1", "status": "processing"},
                {"status": "failed", "error": {"message": "Edit failed."}}
                if outcome == "failed"
                else {"status": "succeeded", "data": [{"url": "https://example.com/out.png"}]},
            ]
        )
    task_execution.process_task(session, task)
    if outcome in {"failed", "late_success"}:
        task.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        task_execution.process_task(session, task)
    for _ in range(2):
        task_execution.process_task(session, task)
    result = client.get(f"/v1/images/generations/{task.task_id}", headers=auth_headers(key)).json()
    account = session.get(CreditAccount, user["id"])
    session.refresh(account)
    if outcome == "unknown":
        assert result["status"] == "submission_unknown"
        assert task.review_required and task.billing_status == "held"
        assert account.available == Decimal("0.77") and account.frozen == Decimal("1.23")
        assert len(calls) == 1 and result["completed"] is None
        expected_entries = ["freeze"]
    elif outcome == "late_success":
        assert result["status"] == "succeeded" and task.timed_out_at is not None
        assert account.available == Decimal("0.77") and account.frozen == 0
        expected_entries = ["freeze", "settle"]
    else:
        assert result["status"] == "failed" and result["completed"] is not None
        assert result["error"]["type"] == "generation_error" and result["data"] == []
        assert account.available == Decimal("2") and account.frozen == 0
        expected_entries = ["freeze", "release"]
    assert [
        row.entry_type for row in session.scalars(select(CreditEntry).order_by(CreditEntry.id))
    ] == expected_entries


def test_edit_auth_balance_and_ownership(client, session, edits):
    key, user, provider, model, _, _, _ = edits
    body = {**EXAMPLE, "model": model.public_id}
    assert client.post("/v1/images/edits", json=body).status_code == 401
    account = session.get(CreditAccount, user["id"])
    account.available = Decimal("0.01")
    session.commit()
    assert submit(client, key, model).status_code == 402
    assert session.scalar(select(Task)) is None
    account.available = Decimal("2")
    provider.is_active = False
    session.commit()
    assert submit(client, key, model).status_code == 503
    provider.is_active = True
    session.commit()
    assert submit(client, key, model, model="missing").status_code == 404
    second_key = create_key(client)
    response = submit(client, key, model)
    task_id = response.json()["id"]
    path = f"/v1/images/generations/{task_id}"
    assert client.get(path, headers=auth_headers(second_key)).status_code == 200
    registered = client.post(
        "/api/account/register",
        json={"email": "other@example.com", "password": "test-password-only"},
    )
    assert registered.status_code == 201
    assert client.get(path, headers=auth_headers(create_key(client))).status_code == 404
