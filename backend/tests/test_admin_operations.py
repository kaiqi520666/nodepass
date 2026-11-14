from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_accounts import register
from test_catalog import add_model
from test_generations import auth_headers, prepare_user

from app.models import (
    AdminAction,
    Asset,
    CreditAccount,
    CreditEntry,
    Task,
    TaskAsset,
    TextCall,
    User,
)
from app.schemas_text import ChatRequest
from app.services.text_billing import prepare_text_call
from app.services.text_catalog import seed_gpt_models


def _action(user_id: int, **overrides):
    values = {
        "actor_user_id": user_id,
        "action": "task.release",
        "target_type": "task",
        "target_id": str(uuid4()),
        "request_id": uuid4(),
        "request_fingerprint": "a" * 64,
        "reason": "test release",
        "amount": Decimal("0.10000000"),
    }
    values.update(overrides)
    return AdminAction(**values)


def _make_admin(client, session):
    response = client.post(
        "/api/account/register",
        json={"email": "admin@example.com", "password": "test-password-only"},
    )
    assert response.status_code == 201, response.text
    user = response.json()
    session.get(User, user["id"]).is_admin = True
    session.commit()
    return user


def _create_image_task(client, session):
    key, user = prepare_user(client, session)
    _, model, _ = add_model(session)
    response = client.post(
        "/v1/images/generations",
        headers=auth_headers(key),
        json={"model": model.public_id, "prompt": "test image"},
    )
    assert response.status_code == 202, response.text
    task = session.scalar(select(Task).where(Task.task_id == UUID(response.json()["id"])))
    assert task is not None
    return task, user


def _task_payload(action="release", reason="人工核实关闭", request_id=None):
    return {
        "action": action,
        "reason": reason,
        "request_id": str(request_id or uuid4()),
    }


def _create_text_call(session, user_id, *, status="processing", age_minutes=60):
    seed_gpt_models(session, "test-upstream-secret")
    call, _, _ = prepare_text_call(
        session,
        user_id,
        ChatRequest(model="gpt-6.1-sol", messages=[{"role": "user", "content": "hi"}]),
    )
    old = datetime.now(UTC) - timedelta(minutes=age_minutes)
    session.execute(
        update(TextCall)
        .where(TextCall.id == call.id)
        .values(status=status, created_at=old, updated_at=old)
    )
    session.commit()
    session.expire_all()
    return session.get(TextCall, call.id)


def test_admin_actions_are_append_only(client, session):
    user = register(client).json()
    action = _action(user["id"])
    session.add(action)
    session.commit()

    with pytest.raises(DBAPIError):
        session.execute(
            update(AdminAction).where(AdminAction.id == action.id).values(reason="changed")
        )
        session.commit()
    session.rollback()
    session.expire_all()
    assert session.get(AdminAction, action.id).reason == "test release"

    with pytest.raises(DBAPIError):
        session.execute(delete(AdminAction).where(AdminAction.id == action.id))
        session.commit()
    session.rollback()
    session.expire_all()
    assert session.get(AdminAction, action.id) is not None


def test_admin_operations_require_admin(client):
    register(client)
    assert client.get("/api/admin/exceptions/summary").status_code == 403
    assert (
        client.post(f"/api/admin/tasks/{uuid4()}/resolve", json=_task_payload()).status_code == 403
    )
    assert (
        client.post(
            f"/api/admin/text-calls/{uuid4()}/resolve",
            json={
                "action": "mark_unknown",
                "reason": "调用中断",
                "request_id": str(uuid4()),
            },
        ).status_code
        == 403
    )


def test_task_requery_is_audited(client, session):
    task, user = _create_image_task(client, session)
    task.status = "submission_unknown"
    task.upstream_task_id = "upstream-1"
    task.review_required = True
    session.commit()
    admin = _make_admin(client, session)

    response = client.post(
        f"/api/admin/tasks/{task.task_id}/resolve",
        json=_task_payload("requery", "重新查询上游"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    session.expire_all()
    task = session.get(Task, task.id)
    assert task.status == "pending"
    assert task.review_required is False
    assert task.resolution == "manual_requeued"
    assert task.next_run_at is not None
    action = session.get(AdminAction, body["audit_id"])
    assert action.action == "task.requery"
    assert action.actor_user_id == admin["id"]
    assert action.amount is None
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 1
    assert body["id"] == str(task.task_id)


def test_task_release_is_idempotent_and_audited(client, session):
    task, user = _create_image_task(client, session)
    frozen = task.frozen_amount
    task.status = "submission_unknown"
    task.review_required = True
    session.commit()
    _make_admin(client, session)
    request_id = uuid4()
    payload = _task_payload("release", "上游未受理", request_id)

    first = client.post(f"/api/admin/tasks/{task.task_id}/resolve", json=payload)
    assert first.status_code == 200, first.text
    body = first.json()
    session.expire_all()
    task = session.get(Task, task.id)
    account = session.get(CreditAccount, user["id"])
    assert task.status == "failed"
    assert task.billing_status == "released"
    assert task.review_required is False
    assert task.resolution == "manual_released"
    assert task.error_code == "manual_release"
    assert task.error_message == "任务已关闭，冻结积分已释放"
    assert task.result_snapshot == []
    assert account.available == Decimal("2.0000")
    assert account.frozen == Decimal("0.0000")
    release = session.scalar(select(CreditEntry).where(CreditEntry.entry_type == "release"))
    assert release.amount == frozen
    action = session.get(AdminAction, body["audit_id"])
    assert action.action == "task.release"
    assert action.amount == frozen
    assert action.credit_entry_id == release.id
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 2

    replay = client.post(f"/api/admin/tasks/{task.task_id}/resolve", json=payload)
    assert replay.status_code == 200
    assert replay.json()["audit_id"] == body["audit_id"]
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 2

    conflict = client.post(
        f"/api/admin/tasks/{task.task_id}/resolve",
        json=_task_payload("release", "另一个原因", request_id),
    )
    assert conflict.status_code == 409
    repeated = client.post(
        f"/api/admin/tasks/{task.task_id}/resolve",
        json=_task_payload("release", "上游未受理", uuid4()),
    )
    assert repeated.status_code == 409


def test_task_retry_transfer_and_ready_result_guard(client, session):
    task, user = _create_image_task(client, session)
    task.status = "transferring"
    task.result_snapshot = [{"url": "https://supplier.invalid/result.png"}]
    session.commit()
    _make_admin(client, session)

    response = client.post(
        f"/api/admin/tasks/{task.task_id}/resolve",
        json=_task_payload("retry_transfer", "重试转存"),
    )
    assert response.status_code == 200, response.text
    session.expire_all()
    task = session.get(Task, task.id)
    assert task.status == "transferring"
    assert task.resolution == "manual_retry_transfer"
    assert task.next_run_at is not None

    asset = Asset(
        user_id=user["id"],
        source_kind="generated",
        status="ready",
        public_url="https://media.example.com/result.png",
    )
    session.add(asset)
    session.flush()
    session.add(TaskAsset(task_id=task.id, role="result", position=0, asset_id=asset.id))
    session.commit()

    blocked = client.post(
        f"/api/admin/tasks/{task.task_id}/resolve",
        json=_task_payload("release", "存在结果"),
    )
    assert blocked.status_code == 409

    listed = client.get(
        "/api/admin/exceptions/tasks",
        params={"status": "transferring", "task_id": str(task.task_id)},
    )
    assert listed.status_code == 200
    row = listed.json()["data"][0]
    assert row["has_ready_result"] is True
    assert row["allowed_actions"] == ["retry_transfer"]


def test_resolve_returns_409_when_worker_holds_lock(client, session, engine):
    task, _ = _create_image_task(client, session)
    task.status = "pending"
    session.commit()
    _make_admin(client, session)

    with Session(engine) as locker:
        locker.scalar(select(Task).where(Task.id == task.id).with_for_update())
        response = client.post(
            f"/api/admin/tasks/{task.task_id}/resolve",
            json=_task_payload("release", "锁冲突测试"),
        )
        assert response.status_code == 409
        locker.rollback()
    session.rollback()


def test_exception_summary_and_lists(client, session):
    task, user = _create_image_task(client, session)
    task.status = "submission_unknown"
    task.review_required = True
    session.commit()
    call = _create_text_call(session, user["id"], status="usage_unknown", age_minutes=5)
    _make_admin(client, session)

    summary = client.get("/api/admin/exceptions/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["tasks"]["submission_unknown"] == 1
    assert body["text_calls"]["usage_unknown"] == 1

    tasks = client.get("/api/admin/exceptions/tasks")
    assert tasks.status_code == 200
    row = next(item for item in tasks.json()["data"] if item["id"] == str(task.task_id))
    assert row["user"]["email"] == user["email"]
    assert row["has_upstream_id"] is False
    assert row["allowed_actions"] == ["release"]
    assert row["last_action"] is None

    text_calls = client.get("/api/admin/exceptions/text-calls")
    assert text_calls.status_code == 200
    text_row = next(item for item in text_calls.json()["data"] if item["id"] == str(call.id))
    assert text_row["status"] == "usage_unknown"
    assert text_row["allowed_actions"] == ["manual_charge", "close_no_charge"]


def test_text_mark_unknown_then_manual_charge_and_replay(client, session):
    user = register(client).json()
    session.get(CreditAccount, user["id"]).available = Decimal("10")
    session.commit()
    call = _create_text_call(session, user["id"])
    _make_admin(client, session)

    mark = client.post(
        f"/api/admin/text-calls/{call.id}/resolve",
        json={
            "action": "mark_unknown",
            "reason": "调用已中断",
            "request_id": str(uuid4()),
        },
    )
    assert mark.status_code == 200, mark.text
    session.expire_all()
    call = session.get(TextCall, call.id)
    assert call.status == "usage_unknown"
    assert call.resolution == "manual_marked_unknown"
    assert call.error_message == "调用已中断，用量待核实"

    request_id = uuid4()
    payload = {
        "action": "manual_charge",
        "amount": "0.12345678",
        "reason": "按上游账单核定",
        "request_id": str(request_id),
    }
    charge = client.post(f"/api/admin/text-calls/{call.id}/resolve", json=payload)
    assert charge.status_code == 200, charge.text
    body = charge.json()
    session.expire_all()
    call = session.get(TextCall, call.id)
    account = session.get(CreditAccount, user["id"])
    assert call.status == "settled_manually"
    assert call.charge_amount == Decimal("0.12345678")
    assert call.cost_amount is None
    assert call.resolution == "manual_charged"
    assert call.error_message == "调用已人工核定"
    assert account.available == Decimal("9.87654322")
    entry = session.scalar(select(CreditEntry).where(CreditEntry.entry_type == "text_charge"))
    assert entry.amount == Decimal("0.12345678")
    action = session.get(AdminAction, body["audit_id"])
    assert action.action == "text.manual_charge"
    assert action.amount == Decimal("0.12345678")
    assert action.credit_entry_id == entry.id

    replay = client.post(f"/api/admin/text-calls/{call.id}/resolve", json=payload)
    assert replay.status_code == 200
    assert replay.json()["audit_id"] == body["audit_id"]
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 1


def test_text_close_no_charge_and_precision_validation(client, session):
    user = register(client).json()
    session.get(CreditAccount, user["id"]).available = Decimal("10")
    session.commit()
    call = _create_text_call(session, user["id"], status="usage_unknown", age_minutes=5)
    _make_admin(client, session)

    invalid = client.post(
        f"/api/admin/text-calls/{call.id}/resolve",
        json={
            "action": "manual_charge",
            "amount": "0.123456789",
            "reason": "超过八位",
            "request_id": str(uuid4()),
        },
    )
    assert invalid.status_code == 422
    missing = client.post(
        f"/api/admin/text-calls/{call.id}/resolve",
        json={
            "action": "manual_charge",
            "reason": "缺少金额",
            "request_id": str(uuid4()),
        },
    )
    assert missing.status_code == 422

    close = client.post(
        f"/api/admin/text-calls/{call.id}/resolve",
        json={
            "action": "close_no_charge",
            "reason": "无可靠用量",
            "request_id": str(uuid4()),
        },
    )
    assert close.status_code == 200, close.text
    session.expire_all()
    call = session.get(TextCall, call.id)
    assert call.status == "closed_no_charge"
    assert call.charge_amount == Decimal("0.00000000")
    assert call.error_message == "调用已关闭，未扣费"
    assert call.resolution == "manual_closed_no_charge"
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 0
    assert session.get(CreditAccount, user["id"]).available == Decimal("10")


def test_text_mark_unknown_rejects_recent_processing(client, session):
    user = register(client).json()
    session.get(CreditAccount, user["id"]).available = Decimal("10")
    session.commit()
    call = _create_text_call(session, user["id"], age_minutes=1)
    _make_admin(client, session)

    response = client.post(
        f"/api/admin/text-calls/{call.id}/resolve",
        json={
            "action": "mark_unknown",
            "reason": "调用可能仍在执行",
            "request_id": str(uuid4()),
        },
    )
    assert response.status_code == 409


def test_audit_list_and_detail(client, session):
    task, _ = _create_image_task(client, session)
    task.status = "submission_unknown"
    session.commit()
    _make_admin(client, session)
    response = client.post(
        f"/api/admin/tasks/{task.task_id}/resolve",
        json=_task_payload("release", "审计列表测试"),
    )
    assert response.status_code == 200
    audit_id = response.json()["audit_id"]

    listed = client.get("/api/admin/audit-actions")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1
    row = next(item for item in body["data"] if item["id"] == audit_id)
    assert row["action"] == "task.release"
    assert "before_snapshot" not in row

    detail = client.get(f"/api/admin/audit-actions/{audit_id}")
    assert detail.status_code == 200
    assert detail.json()["before_snapshot"]["status"] == "submission_unknown"
    assert detail.json()["after_snapshot"]["status"] == "failed"


def test_admin_credit_adjustment_is_audited_and_idempotent(client, session):
    user = register(client).json()
    _make_admin(client, session)
    request_id = uuid4()
    payload = {
        "direction": "increase",
        "amount": "1.23456789",
        "reason": "测试充值",
        "request_id": str(request_id),
    }
    response = client.post(f"/api/admin/users/{user['id']}/credits", json=payload)
    assert response.status_code == 200, response.text
    session.expire_all()
    action = session.scalar(select(AdminAction).where(AdminAction.action == "user.credit_increase"))
    assert action is not None
    assert action.amount == Decimal("1.23456789")
    assert action.target_type == "user"
    entry = session.scalar(select(CreditEntry).where(CreditEntry.entry_type == "admin_credit"))
    assert action.credit_entry_id == entry.id

    replay = client.post(f"/api/admin/users/{user['id']}/credits", json=payload)
    assert replay.status_code == 200
    assert session.scalar(select(func.count()).select_from(AdminAction)) == 1
    conflict = client.post(
        f"/api/admin/users/{user['id']}/credits",
        json={**payload, "reason": "另一个原因"},
    )
    assert conflict.status_code == 409
