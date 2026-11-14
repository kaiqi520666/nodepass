import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from test_catalog import add_model
from test_generations import auth_headers, prepare_user

from app.models import Asset, CreditAccount, CreditEntry, Task, TaskAsset
from app.providers.base import GenerationOutput, GenerationResult
from app.services.task_execution import _transfer_and_settle, process_task


class FakeAdapter:
    def submit(self, task):
        return GenerationResult(state="pending", upstream_id="upstream-1", raw_status="queued")

    def query(self, task):
        return GenerationResult(
            state="succeeded",
            upstream_id=task.upstream_task_id,
            raw_status="completed",
            outputs=(GenerationOutput(url="https://supplier.invalid/result.png"),),
        )


@pytest.mark.parametrize("outcome", ["succeeded", "failed"])
def test_documented_image_flow(client, session, monkeypatch, outcome):
    key, user = prepare_user(client, session)
    headers = auth_headers(key)
    _, model, _ = add_model(session)
    listed = client.get("/v1/models", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == model.public_id
    example_path = (
        Path(__file__).resolve().parents[2]
        / "frontend/src/views/docs/image-generation.example.json"
    )
    payload = json.loads(example_path.read_text())
    payload["model"] = model.public_id
    response = client.post("/v1/images/generations", headers=headers, json=payload)
    assert response.status_code == 202
    submitted = response.json()
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/v1/images/generations"]["post"]["responses"]["202"]
    assert schema["paths"]["/v1/images/generations/{task_id}"]["get"]["responses"]["200"]
    assert set(submitted) == set(
        schema["components"]["schemas"]["QueuedImageGeneration"]["properties"]
    )
    assert submitted["object"] == "image.generation"
    assert submitted["status"] == "queued"
    assert submitted["data"] == []
    assert isinstance(submitted["created"], int)
    assert "completed" not in submitted
    assert "error" not in submitted
    path = f"/v1/images/generations/{submitted['id']}"
    queued = client.get(path, headers=headers).json()
    assert queued["completed"] is None
    assert queued["error"] is None
    session.expire_all()
    stored = session.scalar(select(Task).where(Task.task_id == submitted["id"]))
    assert stored is not None

    if outcome == "failed":
        monkeypatch.setattr(
            FakeAdapter,
            "query",
            lambda _self, task: GenerationResult(
                state="failed",
                upstream_id=task.upstream_task_id,
                raw_status="failed",
                error="Image generation failed.",
            ),
        )
    monkeypatch.setattr(
        "app.services.task_execution._adapter", lambda _provider, _task: FakeAdapter()
    )
    monkeypatch.setattr(
        "app.services.task_execution.decode_output",
        lambda _output: (b"fake-image", "image/png"),
    )
    monkeypatch.setattr(
        "app.services.task_execution.upload_result",
        lambda *_args, **_kwargs: {
            "region": "cn-hongkong",
            "bucket": "nodepass-test",
            "object_key": f"generated/{stored.task_id}/0.png",
            "public_url": "https://image.nodepass.net/generated/result.png",
            "content_type": "image/png",
            "byte_size": 10,
        },
    )

    process_task(session, stored)
    session.expire_all()
    stored = session.scalar(select(Task).where(Task.task_id == submitted["id"]))
    assert stored.status == "pending"
    assert stored.upstream_task_id == "upstream-1"
    pending = client.get(path, headers=headers).json()
    assert pending["status"] == "pending"
    assert pending["data"] == []
    assert pending["completed"] is None

    process_task(session, stored)
    session.expire_all()
    stored = session.scalar(select(Task).where(Task.task_id == submitted["id"]))
    if outcome == "succeeded":
        assert stored.status == "transferring"
        assert session.scalar(select(Asset)) is None
        process_task(session, stored)
        session.expire_all()
        stored = session.scalar(select(Task).where(Task.task_id == submitted["id"]))
    account = session.get(CreditAccount, user["id"])
    result = client.get(path, headers=headers)
    assert result.status_code == 200
    body = result.json()
    assert set(body) == set(
        schema["components"]["schemas"]["ImageGenerationResponse"]["properties"]
    )
    assert body["status"] == outcome
    assert body["object"] == "image.generation"
    assert body["created"] == submitted["created"]
    assert isinstance(body["completed"], int)
    assert body["completed"] >= body["created"]
    assert account.frozen == Decimal("0.0000")
    if outcome == "succeeded":
        assert stored.billing_status == "settled"
        assert account.available == Decimal("0.7700")
        assert body["error"] is None
        assert body["data"] == [{"url": "https://image.nodepass.net/generated/result.png"}]
        assert session.scalar(select(CreditEntry).where(CreditEntry.entry_type == "settle"))
        assert session.scalar(select(Asset))
        assert session.scalar(select(TaskAsset))
    else:
        assert stored.billing_status == "released"
        assert account.available == Decimal("2.0000")
        assert body["data"] == []
        assert body["error"] == {
            "message": "Image generation failed.",
            "type": "generation_error",
        }
        assert session.scalar(select(CreditEntry).where(CreditEntry.entry_type == "release"))
        assert session.scalar(select(Asset)) is None
    stats = client.get("/api/account/dashboard").json()
    assert stats["requests"] == 1
    assert stats["consumed"] == ("1.23000000" if outcome == "succeeded" else "0.00000000")


def test_transfer_guard_skips_released_task(client, session, monkeypatch):
    key, _ = prepare_user(client, session)
    _, model, _ = add_model(session)
    response = client.post(
        "/v1/images/generations",
        headers=auth_headers(key),
        json={"model": model.public_id, "prompt": "test"},
    )
    assert response.status_code == 202
    task = session.scalar(select(Task).where(Task.task_id == UUID(response.json()["id"])))
    assert task is not None
    task.status = "transferring"
    task.billing_status = "released"
    task.result_snapshot = [{"url": "https://supplier.invalid/result.png"}]
    session.commit()

    uploaded = False

    def upload(*_args, **_kwargs):
        nonlocal uploaded
        uploaded = True
        raise AssertionError("upload must not run after release")

    monkeypatch.setattr("app.services.task_execution.upload_result", upload)
    _transfer_and_settle(session, task)
    assert uploaded is False
    assert task.billing_status == "released"
