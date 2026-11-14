from collections import deque
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_generations import auth_headers, prepare_user

from app.core.security import credential_cipher
from app.models import CreditAccount, CreditEntry, Model, Provider, Task, User
from app.providers import MeaiccVideoAdapter, ProviderError
from app.services import task_execution
from app.services.video_catalog import VIDEO_MODELS, seed_video_models


@pytest.fixture
def video_environment(client, session, monkeypatch):
    key, user = prepare_user(client, session)
    session.get(User, user["id"]).is_admin = True
    session.get(CreditAccount, user["id"]).available = Decimal("100.0000")
    assert seed_video_models(session) == 10
    provider = session.scalar(select(Provider))
    provider.is_active = True
    provider.credentials_encrypted = credential_cipher().encrypt(b"fake-upstream-only").decode()
    for model in session.scalars(select(Model)):
        model.is_active = True
    session.commit()
    events = deque()
    calls = []
    uploads = []

    def request(adapter, path, *, method="GET", payload=None):
        calls.append((path, method, payload, adapter.timeout))
        event = events.popleft()
        if isinstance(event, Exception):
            raise event
        return event

    def upload(_session, task_id, position, url, timeout):
        uploads.append((task_id, position, url, timeout))
        return {
            "region": "test",
            "bucket": "test",
            "object_key": f"{task_id}/{position}.mp4",
            "public_url": f"https://media.example.com/{task_id}/{position}.mp4",
            "content_type": "video/mp4",
            "byte_size": 1024,
        }

    monkeypatch.setattr(MeaiccVideoAdapter, "_request", request)
    monkeypatch.setattr(task_execution, "upload_video_result", upload)
    return key, user, provider, events, calls, uploads


def submit(client, session, key, **params):
    response = client.post(
        "/v1/videos",
        headers=auth_headers(key),
        json={"model": "sd-2-c4", "prompt": "offline video test", **params},
    )
    assert response.status_code == 202, response.text
    return session.scalar(select(Task).where(Task.task_id == response.json()["id"]))


def query(client, key, task):
    response = client.get(f"/v1/videos/{task.task_id}", headers=auth_headers(key))
    assert response.status_code == 200, response.text
    return response.json()


def test_seed_exact_ten_models_without_overwriting_admin_edits(session):
    assert seed_video_models(session) == 10
    models = session.scalars(select(Model).order_by(Model.id)).all()
    assert [model.public_id for model in models] == [row[0] for row in VIDEO_MODELS]
    assert all(model.public_id == model.upstream_model_id for model in models)
    assert all(model.pricing_dimensions == [] and not model.is_active for model in models)
    assert all(
        model.prices[0].sale_unit_price == model.prices[0].cost_unit_price for model in models
    )
    assert models[0].capabilities["version"] == "fast"
    assert models[3].capabilities["version"] == "full"
    assert models[8].capabilities["resolutions"] == ["480p"]
    models[0].prices[0].sale_unit_price = Decimal("9.1234")
    session.commit()
    assert seed_video_models(session) == 0
    assert models[0].prices[0].sale_unit_price == Decimal("9.1234")


@pytest.mark.parametrize(
    ("model", "seconds", "expected"),
    [
        ("sd-2-c4", None, "1.8000"),
        ("sd-2-c4", "12", "1.8000"),
        ("sd-2.5-d1-720", "10.12345", "5.46666300"),
    ],
)
def test_success_real_adapter_mapping_transfer_settlement_and_repeat_queries(
    client,
    session,
    video_environment,
    model,
    seconds,
    expected,
):
    key, user, _, events, calls, uploads = video_environment
    refs = [
        {"type": "first_frame", "url": "https://example.com/first.png"},
        {"type": "last_frame", "url": "https://example.com/last.png"},
        {"type": "reference_image", "url": "https://example.com/ref.png"},
        {"type": "reference_video", "url": "https://example.com/ref.mp4"},
        {"type": "reference_audio", "url": "https://example.com/ref.mp3"},
    ]
    params = {"seconds": seconds} if seconds is not None else {}
    task = submit(client, session, key, model=model, references=refs, **params)
    initial = query(client, key, task)
    assert initial["object"] == "video.generation"
    assert initial["completed"] is None and initial["data"] == [] and not initial["timed_out"]
    assert task.frozen_amount == Decimal(expected)
    assert task.quantity == (Decimal(seconds) if model == "sd-2.5-d1-720" else Decimal(1))
    events.extend(
        [
            {"task_id": "fake-1", "status": "PENDING"},
            {"id": "fake-1", "status": "SUCCEEDED", "object": "https://example.com/output.mp4"},
        ]
    )
    task_execution.process_task(session, task)
    wire = calls[0][2]
    assert wire["model"] == model
    assert wire["parameters"] == {
        "duration": float(seconds) if seconds else 10,
        "resolution": "720p",
        "ratio": "16:9",
    }
    assert wire["input"]["media"][-1]["type"] == "reference_voice"
    assert "seconds" not in wire and "references" not in wire
    assert task.status == "pending"
    assert task.next_run_at > datetime.now(UTC) + timedelta(seconds=55)
    assert task_execution.process_next_task(session) is False
    task_execution.process_task(session, task)
    body = query(client, key, task)
    assert body["status"] == "succeeded" and body["completed"] is not None
    assert len(body["data"]) == 1 and body["data"][0]["url"].startswith(
        "https://media.example.com/"
    )
    assert body["error"] is None and not body["timed_out"]
    assert len(uploads) == 1
    for _ in range(3):
        assert query(client, key, task) == body
        task_execution.process_task(session, task)
    assert len(calls) == 2 and len(uploads) == 1
    account = session.get(CreditAccount, user["id"])
    assert account.available == Decimal("100.0000") - Decimal(expected)
    assert account.frozen == 0
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 2
    log = client.get(f"/api/account/tasks/{task.task_id}").json()
    assert log["object"] == "video.generation" and log["media_type"] == "video"
    assert "upstream_task_id" not in body and "result_snapshot" not in log
    stats = client.get("/api/account/dashboard").json()
    assert stats["requests"] == 1
    assert Decimal(stats["consumed"]) == Decimal(expected)
    assert Decimal(stats["available"]) == account.available


@pytest.mark.parametrize(
    "params",
    [
        {"model": "sd-2.5-d1-720"},
        {"seconds": 3},
        {"seconds": 16},
        {"seconds": "NaN"},
        {"seconds": "Infinity"},
        {"resolution": "480p"},
        {"aspect_ratio": "4:3"},
        {"extra": True},
        {"references": [{"type": "reference_audio", "url": "http://example.com/a.mp3"}]},
        {"references": [{"type": "first_frame", "url": "https://127.0.0.1/a.png"}]},
        {"references": [{"type": "first_frame", "url": "https://localhost/a.png"}]},
        {"references": [{"type": "first_frame", "url": "https://user:pass@example.com/a.png"}]},
        {"references": [{"type": "reference_image", "url": "https://example.com/a.png"}] * 10},
        {"references": [{"type": "first_frame", "url": "https://example.com/a.png"}] * 2},
    ],
)
def test_invalid_video_requests_never_freeze(client, session, video_environment, params):
    key, user, *_ = video_environment
    response = client.post(
        "/v1/videos",
        headers=auth_headers(key),
        json={"model": "sd-2-c4", "prompt": "test", **params},
    )
    assert response.status_code == 422, response.text
    assert session.scalar(select(Task)) is None
    assert session.scalar(select(CreditEntry)) is None
    assert session.get(CreditAccount, user["id"]).available == Decimal("100.0000")


def test_video_auth_ownership_and_image_route_separation(client, session, video_environment):
    key, _, *_ = video_environment
    assert client.post("/v1/videos", json={"model": "sd-2-c4", "prompt": "test"}).status_code == 401
    task = submit(client, session, key)
    assert (
        client.get(f"/v1/images/generations/{task.task_id}", headers=auth_headers(key)).status_code
        == 404
    )
    another_key = client.post("/api/account/keys", json={"name": "another"}).json()["key"]
    assert query(client, another_key, task)["id"] == str(task.task_id)
    client.post(
        "/api/account/register", json={"email": "other@example.com", "password": "test-password"}
    )
    other_key = client.post("/api/account/keys", json={"name": "other"}).json()["key"]
    assert (
        client.get(f"/v1/videos/{task.task_id}", headers=auth_headers(other_key)).status_code == 404
    )


@pytest.mark.parametrize("during_submit", [True, False])
def test_explicit_failure_releases_all_frozen_credit_once(
    client,
    session,
    video_environment,
    during_submit,
):
    key, user, _, events, *_ = video_environment
    task = submit(client, session, key)
    if not during_submit:
        events.append({"id": "fake", "status": "RUNNING"})
        task_execution.process_task(session, task)
    events.append({"status": "FAILED: rejected"})
    task_execution.process_task(session, task)
    task_execution.process_task(session, task)
    body = query(client, key, task)
    assert body["status"] == "failed" and body["data"] == []
    assert body["error"]["type"] == "generation_error" and body["completed"] is not None
    assert task.billing_status == "released"
    account = session.get(CreditAccount, user["id"])
    assert account.available == Decimal("100.0000") and account.frozen == 0
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 2


def test_snapshot_times_no_poll_cap_and_late_success(client, session, video_environment):
    key, _, provider, events, calls, _ = video_environment
    provider.request_config = {
        "timeout_seconds": 777,
        "poll_interval_seconds": 7200,
        "task_timeout_seconds": 14400,
    }
    session.commit()
    task = submit(client, session, key)
    assert 14399 <= (task.deadline_at - task.created_at).total_seconds() <= 14401
    provider.request_config = {
        "timeout_seconds": 10,
        "poll_interval_seconds": 1,
        "task_timeout_seconds": 30,
    }
    task.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert query(client, key, task)["timed_out"]
    events.extend(
        [
            {"id": "fake", "status": "RUNNING"},
            {"id": "fake", "status": "SUCCEEDED", "object": "https://example.com/result.mp4"},
        ]
    )
    task_execution.process_task(session, task)
    assert (task.next_run_at - datetime.now(UTC)).total_seconds() > 7190
    task_execution.process_task(session, task)
    assert all(call[3] == 777 for call in calls)
    assert query(client, key, task)["timed_out"]
    assert task.status == "succeeded" and task.timed_out_at is not None


def test_timeout_is_historical_and_catches_unknown_submissions(client, session, video_environment):
    key, _, _, events, *_ = video_environment
    task = submit(client, session, key)
    task.status = "submission_unknown"
    task.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert query(client, key, task)["timed_out"]
    assert task.billing_status == "held"
    task.status = "queued"
    task.deadline_at = datetime.now(UTC) + timedelta(seconds=1)
    session.commit()
    events.append({"id": "fake", "status": "SUCCEEDED", "object": "https://example.com/a.mp4"})
    task_execution.process_task(session, task)
    assert not query(client, key, task)["timed_out"]
    assert not task.has_timed_out(datetime.now(UTC) + timedelta(days=10))


@pytest.mark.parametrize("interrupted", [True, False])
def test_unknown_submission_keeps_freeze_and_is_not_resubmitted(
    client,
    session,
    video_environment,
    interrupted,
):
    key, user, _, events, calls, _ = video_environment
    task = submit(client, session, key)
    if interrupted:
        task.status = "submitting"
        session.commit()
    else:
        events.append(ProviderError("mock connection interrupted"))
    task_execution.process_task(session, task)
    assert task.status == "submission_unknown" and task.review_required
    assert task.billing_status == "held"
    assert task_execution.process_next_task(session) is False
    task_execution.process_task(session, task)
    assert len(calls) == (0 if interrupted else 1)
    assert session.get(CreditAccount, user["id"]).frozen == Decimal("1.8000")
    assert query(client, key, task)["data"] == []


def test_transfer_failure_and_service_restart_retry_saved_result_only(
    client,
    session,
    video_environment,
    monkeypatch,
):
    key, _, _, events, calls, uploads = video_environment
    task = submit(client, session, key)
    events.append({"id": "fake", "status": "SUCCEEDED", "object": "https://example.com/result.mp4"})
    upload = task_execution.upload_video_result

    def fail(*_args):
        raise OSError("mock storage unavailable")

    monkeypatch.setattr(task_execution, "upload_video_result", fail)
    task_execution.process_task(session, task)
    assert task.status == "transferring" and task.billing_status == "held"
    assert task.result_snapshot[0]["url"] == "https://example.com/result.mp4"
    assert query(client, key, task)["data"] == []
    monkeypatch.setattr(task_execution, "upload_video_result", upload)
    task.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    with Session(session.bind, expire_on_commit=False) as restarted:
        assert task_execution.process_next_task(restarted)
    session.expire_all()
    assert query(client, key, task)["status"] == "succeeded"
    assert len(calls) == 1 and len(uploads) == 1
    assert task.error_message is None and task.error_code is None


def test_restart_processing_task_and_request_failure_continue_polling(
    client,
    session,
    video_environment,
):
    key, _, _, events, calls, _ = video_environment
    task = submit(client, session, key)
    events.append({"id": "fake", "status": "RUNNING"})
    task_execution.process_task(session, task)
    events.append(ProviderError("mock query timeout"))
    task.next_run_at = datetime.now(UTC)
    session.commit()
    with Session(session.bind) as restarted:
        assert task_execution.process_next_task(restarted)
    session.expire_all()
    assert task.status == "processing" and task.billing_status == "held"
    assert len(calls) == 2
    assert task.next_run_at > datetime.now(UTC)


def test_video_admin_preserves_config_and_validates_defaults(client, session, video_environment):
    _, _, provider, *_ = video_environment
    listed = client.get("/api/admin/models").json()["data"]
    assert len(listed) == 10
    payload = listed[0]
    model_id = payload.pop("id")
    payload["capabilities"]["max_reference_images"] = 42
    assert client.put(f"/api/admin/models/{model_id}", json=payload).status_code == 200
    for change in [
        {"pricing_dimensions": ["resolution"]},
        {"capabilities": {**payload["capabilities"], "defaults": {}}},
        {"capabilities": {**payload["capabilities"], "min_seconds": "100"}},
        {"prices": [{**payload["prices"][0], "sale_unit": "image"}]},
    ]:
        bad = {**deepcopy(payload), **change}
        assert client.put(f"/api/admin/models/{model_id}", json=bad).status_code == 422
    config = client.get("/api/admin/providers").json()["data"][0]
    config.pop("id")
    config.pop("has_credentials")
    config["request_config"] = {
        "timeout_seconds": 900,
        "poll_interval_seconds": 3600,
        "task_timeout_seconds": 14400,
    }
    assert client.put(f"/api/admin/providers/{provider.id}", json=config).status_code == 200
    for field in config["request_config"]:
        bad = deepcopy(config)
        bad["request_config"][field] = 0
        assert client.put(f"/api/admin/providers/{provider.id}", json=bad).status_code == 422
    public = client.get("/api/public/models")
    assert public.status_code == 200
    for secret in ("cost_unit_price", "defaults", "provider_id", "upstream_model_id"):
        assert secret not in public.text


def test_video_insufficient_credit_and_missing_or_disabled_model(
    client,
    session,
    video_environment,
):
    key, user, provider, *_ = video_environment
    account = session.get(CreditAccount, user["id"])
    account.available = Decimal("0.0000")
    session.commit()
    payload = {"model": "sd-2-c4", "prompt": "offline test"}
    assert client.post("/v1/videos", headers=auth_headers(key), json=payload).status_code == 402
    assert (
        client.post(
            "/v1/videos", headers=auth_headers(key), json={**payload, "model": "missing"}
        ).status_code
        == 404
    )
    provider.is_active = False
    session.commit()
    assert client.post("/v1/videos", headers=auth_headers(key), json=payload).status_code == 503
    assert session.scalar(select(Task)) is None
    assert session.scalar(select(CreditEntry)) is None
