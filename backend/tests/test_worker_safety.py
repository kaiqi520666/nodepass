import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from test_admin_operations import _create_image_task, _make_admin, _task_payload
from test_task_execution import FakeAdapter

from app import worker
from app.core.security import credential_cipher
from app.models import AdminAction, Asset, CreditAccount, CreditEntry, Provider, Task, TaskAsset
from app.providers.base import GenerationResult, ProviderError
from app.schemas_admin import TaskResolveRequest
from app.services import task_execution
from app.services.admin_operations import resolve_task


@pytest.mark.parametrize(
    "snapshot",
    [
        [{"url": "https://supplier.invalid/a.png", "unknown": True}],
        [{}],
        [],
        [None],
        [{"url": 42}],
        [{"url": "https://supplier.invalid/a.png", "content_type": None}],
        {"url": "https://supplier.invalid/a.png"},
        [{"b64_json": "invalid base64"}],
    ],
)
def test_bad_result_pauses_and_worker_can_process_next_task(client, session, monkeypatch, snapshot):
    task, user = _create_image_task(client, session)
    task.status = "transferring"
    task.result_snapshot = snapshot
    session.commit()
    assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.review_required
    assert task.next_run_at is None
    assert task.status == "transferring" and task.billing_status == "held"
    updated = task.updated_at
    assert not task_execution.process_next_task(session)
    session.refresh(task)
    assert task.updated_at == updated
    assert session.get(CreditAccount, user["id"]).frozen == task.frozen_amount
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 1

    next_task = Task(
        user_id=task.user_id,
        model_id=task.model_id,
        provider_id=task.provider_id,
        price_id=task.price_id,
        frozen_amount=Decimal(0),
        cost_amount=Decimal(0),
        model_snapshot=task.model_snapshot,
        provider_snapshot=task.provider_snapshot,
        request_params=task.request_params,
    )
    session.add(next_task)
    session.commit()
    monkeypatch.setattr(task_execution, "_adapter", lambda *_args: FakeAdapter())
    assert task_execution.process_next_task(session)
    session.refresh(next_task)
    assert next_task.status == "pending"


@pytest.mark.parametrize("problem", ["credentials", "adapter", "snapshot"])
@pytest.mark.parametrize("stage", ["queued", "processing"])
def test_configuration_errors_pause_without_refunding_and_are_actionable(
    client, session, problem, stage
):
    task, user = _create_image_task(client, session)
    task.status = stage
    if stage == "processing":
        task.upstream_task_id = "original-upstream-id"
    if problem == "adapter":
        session.get(Provider, task.provider_id).credentials_encrypted = (
            credential_cipher().encrypt(b"test-only").decode()
        )
    elif problem == "snapshot":
        session.get(Provider, task.provider_id).credentials_encrypted = (
            credential_cipher().encrypt(b"test-only").decode()
        )
        task.provider_snapshot = {}
    session.commit()
    assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.status == stage and task.review_required
    assert task.billing_status == "held" and task.next_run_at is None
    updated = task.updated_at
    assert not task_execution.process_next_task(session)
    session.refresh(task)
    assert task.updated_at == updated
    assert session.get(CreditAccount, user["id"]).frozen == task.frozen_amount
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 1
    _make_admin(client, session)
    rows = client.get("/api/admin/exceptions/tasks").json()["data"]
    row = next(row for row in rows if row["id"] == str(task.task_id))
    assert row["review_required"]
    assert row["allowed_actions"] == (
        ["retry_submit", "release"] if stage == "queued" else ["requery", "release"]
    )
    assert row["error_code"] == "review_required"
    assert row["error_message"]


def test_storage_configuration_pauses_without_retrying(client, session):
    task, user = _create_image_task(client, session)
    task.status = "transferring"
    task.result_snapshot = [{"b64_json": "eA=="}]
    session.commit()
    assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.review_required and task.next_run_at is None
    assert task.error_message == "OSS 配置或权限不可用，已暂停等待核实"
    assert session.get(CreditAccount, user["id"]).frozen == task.frozen_amount
    updated = task.updated_at
    assert not task_execution.process_next_task(session)
    session.refresh(task)
    assert task.updated_at == updated


@pytest.mark.parametrize("explicit", [False, True])
def test_submit_errors_never_automatically_resubmit(client, session, monkeypatch, explicit):
    task, user = _create_image_task(client, session)
    adapter = MagicMock()
    adapter.submit.side_effect = ProviderError("mock rejection", explicit_failure=explicit)
    monkeypatch.setattr(task_execution, "_adapter", lambda *_args: adapter)
    assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.status == ("failed" if explicit else "submission_unknown")
    assert task.billing_status == ("released" if explicit else "held")
    assert task.next_run_at is None
    assert not task_execution.process_next_task(session)
    assert adapter.submit.call_count == 1
    account = session.get(CreditAccount, user["id"])
    assert account.frozen == (Decimal(0) if explicit else task.frozen_amount)


@pytest.mark.parametrize("stage", ["submitting", "processing"])
def test_unexpected_exception_uses_persisted_stage_and_does_not_leak_payload(
    client, session, monkeypatch, caplog, stage
):
    task, user = _create_image_task(client, session)
    adapter = MagicMock()
    if stage == "processing":
        task.status = "processing"
        task.upstream_task_id = "original-upstream-id"
        session.commit()
    adapter.submit.side_effect = TypeError("SECRET upstream URL and credentials")
    adapter.query.side_effect = TypeError("SECRET upstream URL and credentials")
    monkeypatch.setattr(task_execution, "_adapter", lambda *_args: adapter)
    with caplog.at_level(logging.WARNING):
        assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.status == ("submission_unknown" if stage == "submitting" else "processing")
    assert task.review_required and task.next_run_at is None
    assert task.billing_status == "held"
    assert "SECRET" not in task.error_message
    assert "SECRET" not in caplog.text
    assert str(task.task_id) in caplog.text and "TypeError" in caplog.text
    assert session.get(CreditAccount, user["id"]).frozen == task.frozen_amount


@pytest.mark.parametrize("explicit", [False, True])
def test_query_errors_keep_original_id_and_credit(client, session, monkeypatch, explicit):
    task, user = _create_image_task(client, session)
    task.status = "processing"
    task.upstream_task_id = "original-upstream-id"
    session.commit()
    adapter = MagicMock()
    adapter.query.side_effect = ProviderError("HTTP 404", explicit_failure=explicit)
    monkeypatch.setattr(task_execution, "_adapter", lambda *_args: adapter)
    assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.status == "processing" and task.billing_status == "held"
    assert task.upstream_task_id == "original-upstream-id"
    assert task.review_required is explicit
    assert (task.next_run_at is None) is explicit
    assert session.get(CreditAccount, user["id"]).frozen == task.frozen_amount
    adapter.submit.assert_not_called()


def test_invalid_upstream_id_does_not_leave_database_error_at_queue_head(
    client, session, monkeypatch, caplog
):
    task, _ = _create_image_task(client, session)
    adapter = MagicMock()
    adapter.submit.return_value = GenerationResult("pending", upstream_id="a" * 201)
    monkeypatch.setattr(task_execution, "_adapter", lambda *_args: adapter)
    with caplog.at_level(logging.ERROR):
        assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.status == "submission_unknown" and task.review_required
    assert task.billing_status == "held"
    assert not task_execution.process_next_task(session)
    assert "DataError" in caplog.text and "a" * 201 not in caplog.text


def test_database_outage_is_not_misclassified_as_task_failure(client, session, monkeypatch):
    task, _ = _create_image_task(client, session)
    monkeypatch.setattr(
        task_execution,
        "_process_task",
        MagicMock(side_effect=OperationalError(None, None, RuntimeError("offline"))),
    )
    with pytest.raises(OperationalError):
        task_execution.process_task(session, task)
    session.rollback()
    session.refresh(task)
    assert task.status == "queued" and not task.review_required
    assert task.error_message is None


def test_retry_submit_is_audited_idempotent_and_preserves_snapshot(client, session, monkeypatch):
    task, _ = _create_image_task(client, session)
    task.review_required = True
    task.next_run_at = None
    session.commit()
    snapshot = task.provider_snapshot.copy()
    _make_admin(client, session)
    payload = _task_payload("retry_submit", "修复当前供应商凭证")
    first = client.post(f"/api/admin/tasks/{task.task_id}/resolve", json=payload)
    assert first.status_code == 200, first.text
    replay = client.post(f"/api/admin/tasks/{task.task_id}/resolve", json=payload)
    assert replay.status_code == 200 and replay.json()["audit_id"] == first.json()["audit_id"]
    session.refresh(task)
    assert not task.review_required and task.status == "queued"
    assert task.provider_snapshot == snapshot
    assert task.resolution == "manual_requeued" and task.next_run_at <= datetime.now(UTC)
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 1
    action = session.get(AdminAction, first.json()["audit_id"])
    assert action.action == "task.retry_submit"
    assert action.before_snapshot["review_required"] is True
    assert action.after_snapshot["review_required"] is False

    adapter = MagicMock()
    adapter.submit.return_value = GenerationResult("pending", upstream_id="one-submit-only")
    monkeypatch.setattr(task_execution, "_adapter", lambda *_args: adapter)
    assert task_execution.process_next_task(session)
    assert not task_execution.process_next_task(session)
    replay = client.post(f"/api/admin/tasks/{task.task_id}/resolve", json=payload)
    assert replay.status_code == 200
    adapter.submit.assert_called_once()
    assert session.scalar(select(func.count()).select_from(AdminAction)) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("review_required", False),
        ("upstream_task_id", "already-submitted"),
        ("submitted_at", datetime.now(UTC)),
        ("result_snapshot", [{"url": "https://supplier.invalid/result.png"}]),
        ("status", "submitting"),
        ("status", "submission_unknown"),
        ("status", "pending"),
        ("billing_status", "released"),
    ],
)
def test_retry_submit_rejects_unsafe_states(client, session, field, value):
    task, _ = _create_image_task(client, session)
    task.review_required = True
    setattr(task, field, value)
    session.commit()
    _make_admin(client, session)
    response = client.post(
        f"/api/admin/tasks/{task.task_id}/resolve",
        json=_task_payload("retry_submit", "不能重新提交在途任务"),
    )
    assert response.status_code == 409, response.text
    assert session.scalar(select(func.count()).select_from(AdminAction)) == 0


def test_paused_queued_release_is_idempotent(client, session):
    task, user = _create_image_task(client, session)
    task.review_required = True
    session.commit()
    _make_admin(client, session)
    payload = _task_payload("release", "配置无法恢复，关闭任务")
    first = client.post(f"/api/admin/tasks/{task.task_id}/resolve", json=payload)
    assert first.status_code == 200, first.text
    replay = client.post(f"/api/admin/tasks/{task.task_id}/resolve", json=payload)
    assert replay.status_code == 200
    session.refresh(task)
    account = session.get(CreditAccount, user["id"], populate_existing=True)
    assert account.available == Decimal("2") and account.frozen == 0
    assert task.billing_status == "released"
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 2
    assert session.scalar(select(func.count()).select_from(AdminAction)) == 1


def test_retry_submit_requires_admin_and_respects_worker_lock(client, session, engine):
    task, _ = _create_image_task(client, session)
    task.review_required = True
    session.commit()
    path = f"/api/admin/tasks/{task.task_id}/resolve"
    assert client.post(path, json=_task_payload("retry_submit")).status_code == 403
    _make_admin(client, session)
    with Session(engine) as locker:
        locker.scalar(select(Task).where(Task.id == task.id).with_for_update())
        assert client.post(path, json=_task_payload("retry_submit")).status_code == 409
        locker.rollback()
    session.rollback()


def test_bad_snapshot_does_not_prevent_settling_existing_ready_result(client, session):
    task, user = _create_image_task(client, session)
    task.status = "transferring"
    task.result_snapshot = [{"unknown": "invalid snapshot"}]
    asset = Asset(
        user_id=user["id"],
        source_kind="generated",
        status="ready",
        public_url="https://media.example.com/existing.png",
    )
    session.add(asset)
    session.flush()
    session.add(TaskAsset(task_id=task.id, role="result", position=0, asset_id=asset.id))
    session.commit()
    assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.status == "succeeded" and task.billing_status == "settled"
    assert session.get(CreditAccount, user["id"]).frozen == 0


def test_queued_task_with_execution_record_is_never_submitted(client, session, monkeypatch):
    task, _ = _create_image_task(client, session)
    task.upstream_task_id = "already-submitted"
    session.commit()
    adapter = MagicMock()
    monkeypatch.setattr(task_execution, "_adapter", lambda *_args: adapter)
    assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.status == "submission_unknown" and task.review_required
    adapter.submit.assert_not_called()
    _make_admin(client, session)
    row = client.get("/api/admin/exceptions/tasks").json()["data"][0]
    assert row["allowed_actions"] == ["requery", "release"]


def test_result_pause_rolls_back_partial_asset_writes(client, session, monkeypatch):
    task, user = _create_image_task(client, session)
    task.status = "transferring"
    session.commit()

    def fail(session, task):
        session.add(Asset(user_id=task.user_id, source_kind="generated", status="ready"))
        session.flush()
        task.billing_status = "settled"
        raise TypeError("unexpected failure before settlement commit")

    monkeypatch.setattr(task_execution, "_transfer_and_settle", fail)
    assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.review_required and task.billing_status == "held"
    assert session.scalar(select(func.count()).select_from(Asset)) == 0
    assert session.get(CreditAccount, user["id"]).frozen == task.frozen_amount
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 1


@pytest.mark.parametrize("failure", [OSError, TypeError])
def test_transfer_error_does_not_overwrite_release_during_rollback(
    client, session, engine, monkeypatch, failure
):
    task, user = _create_image_task(client, session)
    task.status = "transferring"
    session.commit()
    admin = _make_admin(client, session)
    task_uuid = task.task_id
    rollback = session.rollback

    def rollback_and_release():
        rollback()
        monkeypatch.setattr(session, "rollback", rollback)
        with Session(engine, expire_on_commit=False) as administrator:
            resolve_task(
                administrator,
                admin["id"],
                task_uuid,
                TaskResolveRequest(**_task_payload("release", "转存回滚期间人工释放")),
            )

    monkeypatch.setattr(session, "rollback", rollback_and_release)
    monkeypatch.setattr(
        task_execution, "_transfer_and_settle", MagicMock(side_effect=failure("transfer failed"))
    )
    assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.status == "failed" and task.billing_status == "released"
    assert task.error_code == "manual_release" and task.resolution == "manual_released"
    assert not task.review_required and task.next_run_at is None
    assert session.get(CreditAccount, user["id"], populate_existing=True).frozen == 0
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 2


def test_transfer_error_does_not_overwrite_retry_transfer_during_rollback(
    client, session, engine, monkeypatch
):
    task, _ = _create_image_task(client, session)
    task.status = "transferring"
    task.result_snapshot = [{"url": "https://supplier.invalid/result.png"}]
    session.commit()
    admin = _make_admin(client, session)
    task_uuid = task.task_id
    rollback = session.rollback

    def rollback_and_retry():
        rollback()
        monkeypatch.setattr(session, "rollback", rollback)
        with Session(engine, expire_on_commit=False) as administrator:
            resolve_task(
                administrator,
                admin["id"],
                task_uuid,
                TaskResolveRequest(**_task_payload("retry_transfer", "转存回滚期间重试")),
            )

    monkeypatch.setattr(session, "rollback", rollback_and_retry)
    monkeypatch.setattr(
        task_execution, "_transfer_and_settle", MagicMock(side_effect=TypeError("transfer failed"))
    )
    assert task_execution.process_next_task(session)
    session.refresh(task)
    assert task.status == "transferring"
    assert task.billing_status == "held"
    assert not task.review_required
    assert task.resolution == "manual_retry_transfer"


def test_retry_submit_does_not_reset_task_paused_again_on_same_snapshot(client, session):
    task, _ = _create_image_task(client, session)
    assert task_execution.process_next_task(session)
    _make_admin(client, session)
    payload = _task_payload("retry_submit", "原配置不可恢复，检查暂停")
    response = client.post(f"/api/admin/tasks/{task.task_id}/resolve", json=payload)
    assert response.status_code == 200
    assert task_execution.process_next_task(session)
    session.refresh(task)
    updated = task.updated_at
    assert task.review_required
    replay = client.post(f"/api/admin/tasks/{task.task_id}/resolve", json=payload)
    assert replay.status_code == 200
    session.refresh(task)
    assert task.review_required and task.updated_at == updated
    assert not task_execution.process_next_task(session)


def test_retry_submit_checks_ready_result_and_request_fingerprint(client, session):
    task, user = _create_image_task(client, session)
    task.review_required = True
    session.commit()
    _make_admin(client, session)
    payload = _task_payload("retry_submit", "恢复之前核实配置")
    first = client.post(f"/api/admin/tasks/{task.task_id}/resolve", json=payload)
    assert first.status_code == 200
    conflict = client.post(
        f"/api/admin/tasks/{task.task_id}/resolve",
        json={**payload, "reason": "不同原因不得重放"},
    )
    assert conflict.status_code == 409
    task.review_required = True
    asset = Asset(user_id=user["id"], source_kind="generated", status="ready")
    session.add(asset)
    session.flush()
    session.add(TaskAsset(task_id=task.id, role="result", position=0, asset_id=asset.id))
    session.commit()
    for action in ("retry_submit", "release"):
        blocked = client.post(
            f"/api/admin/tasks/{task.task_id}/resolve",
            json=_task_payload(action, "存在已就绪素材"),
        )
        assert blocked.status_code == 409


def test_retry_submit_migration_matches_models_and_round_trips(session):
    config = Config("alembic.ini")
    command.check(config)
    command.downgrade(config, "20261115_0013")
    command.upgrade(config, "head")
    command.check(config)


def test_migration_downgrade_refuses_to_discard_new_audit_actions(client, session):
    task, _ = _create_image_task(client, session)
    task.review_required = True
    session.commit()
    _make_admin(client, session)
    response = client.post(
        f"/api/admin/tasks/{task.task_id}/resolve",
        json=_task_payload("retry_submit", "审计记录不可删除"),
    )
    assert response.status_code == 200
    session.rollback()
    with pytest.raises(IntegrityError):
        command.downgrade(Config("alembic.ini"), "20261115_0013")
    assert session.get(AdminAction, response.json()["audit_id"]).action == "task.retry_submit"
    session.rollback()
    command.check(Config("alembic.ini"))


def test_worker_recovers_from_database_failure_without_logging_secrets(monkeypatch, caplog):
    factory = MagicMock()
    monkeypatch.setattr(worker, "get_session_factory", lambda: factory)
    process = MagicMock(
        side_effect=[OperationalError(None, None, RuntimeError("SECRET database URL")), False]
    )
    monkeypatch.setattr(worker, "process_next_task", process)
    monkeypatch.setattr("sys.argv", ["worker"])
    sleeps = []

    def sleep(interval):
        sleeps.append(interval)
        if len(sleeps) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", sleep)
    with caplog.at_level(logging.WARNING), pytest.raises(KeyboardInterrupt):
        worker.main()
    assert process.call_count == 2
    assert sleeps == [2.0, 2.0]
    assert "OperationalError" in caplog.text and "SECRET" not in caplog.text


def test_worker_once_returns_failure_on_database_error(monkeypatch):
    monkeypatch.setattr("sys.argv", ["worker", "--once"])
    factory = MagicMock()
    monkeypatch.setattr(worker, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        worker,
        "process_next_task",
        MagicMock(side_effect=OperationalError(None, None, RuntimeError("database unavailable"))),
    )
    assert worker.main() == 1
