import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.money import money
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
from app.schemas_admin import TaskResolveRequest, TextResolveRequest

TASK_ACTIVE_IDLE = timedelta(minutes=15)
TASK_TRANSFER_IDLE = timedelta(minutes=10)
TEXT_ACTIVE_IDLE = timedelta(minutes=30)
TEXT_SAFETY_MARGIN = timedelta(minutes=15)


def normalize_reason(reason: str) -> str:
    return " ".join(reason.split())


def request_fingerprint(
    action: str,
    target_type: str,
    target_id: str,
    amount: Decimal | None,
    reason: str,
) -> str:
    payload = {
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "amount": format(amount, ".8f") if amount is not None else None,
        "reason": normalize_reason(reason),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _amount_text(value: Decimal | None) -> str | None:
    return format(value, ".8f") if value is not None else None


def _snapshot_task(task: Task) -> dict:
    return {
        "status": task.status,
        "billing_status": task.billing_status,
        "review_required": task.review_required,
        "frozen_amount": _amount_text(task.frozen_amount),
        "error_code": task.error_code,
        "resolution": task.resolution,
    }


def _snapshot_text(call: TextCall) -> dict:
    return {
        "status": call.status,
        "charge_amount": _amount_text(call.charge_amount),
        "cost_amount": _amount_text(call.cost_amount),
        "error_message": call.error_message,
        "resolution": call.resolution,
    }


def snapshot_account(account: CreditAccount) -> dict:
    return {
        "available": _amount_text(account.available),
        "frozen": _amount_text(account.frozen),
    }


def _lock_nowait(session: Session, statement):
    try:
        return session.scalar(statement)
    except OperationalError as exc:
        if getattr(exc.orig, "sqlstate", None) == "55P03":
            session.rollback()
            raise HTTPException(409, "目标正在被后台处理，请稍后重试") from exc
        raise


def _has_ready_result(session: Session, task_id: int) -> bool:
    count = session.scalar(
        select(func.count())
        .select_from(TaskAsset)
        .join(Asset, Asset.id == TaskAsset.asset_id)
        .where(
            TaskAsset.task_id == task_id,
            TaskAsset.role == "result",
            Asset.status == "ready",
        )
    )
    return bool(count)


def task_allowed_actions(task: Task, ready_result: bool) -> list[str]:
    if task.billing_status != "held":
        return []
    if task.status == "queued":
        if (
            task.review_required
            and not task.upstream_task_id
            and task.submitted_at is None
            and not task.result_snapshot
            and not ready_result
        ):
            return ["retry_submit", "release"]
        return []
    if task.status == "submission_unknown":
        actions = ["requery"] if task.upstream_task_id else []
        return [*actions, "release"]
    if task.status in {"pending", "processing"}:
        return ["requery", "release"]
    if task.status == "transferring":
        actions = ["retry_transfer"] if task.result_snapshot or ready_result else []
        if not ready_result:
            actions.append("release")
        return actions
    return []


def _text_mark_unknown_ready(call: TextCall, now: datetime) -> bool:
    if call.status != "processing":
        return False
    raw_timeout = call.price_snapshot.get("timeout_seconds", 0)
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        timeout = 0
    return call.updated_at <= now - TEXT_ACTIVE_IDLE and call.created_at <= (
        now - timedelta(seconds=timeout) - TEXT_SAFETY_MARGIN
    )


def text_allowed_actions(call: TextCall, now: datetime) -> list[str]:
    if call.status == "processing":
        return ["mark_unknown"] if _text_mark_unknown_ready(call, now) else []
    if call.status == "usage_unknown":
        return ["manual_charge", "close_no_charge"]
    return []


def _last_action(session: Session, target_type: str, target_id: str) -> dict | None:
    row = session.execute(
        select(AdminAction, User.email)
        .join(User, User.id == AdminAction.actor_user_id)
        .where(
            AdminAction.target_type == target_type,
            AdminAction.target_id == target_id,
        )
        .order_by(AdminAction.created_at.desc(), AdminAction.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    action, email = row
    return {
        "action": action.action,
        "actor_email": email,
        "created_at": _iso(action.created_at),
    }


def _task_item(session: Session, task: Task, email: str, now: datetime) -> dict:
    ready = _has_ready_result(session, task.id)
    snapshot = task.model_snapshot or {}
    return {
        "id": str(task.task_id),
        "user": {"id": task.user_id, "email": email},
        "model": snapshot.get("public_id", ""),
        "media_type": snapshot.get("media_type", ""),
        "status": task.status,
        "billing_status": task.billing_status,
        "frozen_amount": _amount_text(task.frozen_amount),
        "created": int(task.created_at.timestamp()),
        "updated": int(task.updated_at.timestamp()),
        "waiting_seconds": max(0, int((now - task.created_at).total_seconds())),
        "idle_seconds": max(0, int((now - task.updated_at).total_seconds())),
        "upstream_status": task.upstream_status,
        "has_upstream_id": bool(task.upstream_task_id),
        "has_ready_result": ready,
        "review_required": task.review_required,
        "error_code": task.error_code if task.review_required else None,
        "error_message": task.error_message if task.review_required else None,
        "resolution": task.resolution,
        "allowed_actions": task_allowed_actions(task, ready),
        "last_action": _last_action(session, "task", str(task.task_id)),
    }


def _text_item(
    session: Session, call: TextCall, email: str, available: Decimal, now: datetime
) -> dict:
    return {
        "id": str(call.id),
        "user": {"id": call.user_id, "email": email, "available": _amount_text(available)},
        "model": call.price_snapshot.get("public_id", ""),
        "endpoint": f"/v1/{call.endpoint}",
        "status": call.status,
        "created": int(call.created_at.timestamp()),
        "updated": int(call.updated_at.timestamp()),
        "waiting_seconds": max(0, int((now - call.created_at).total_seconds())),
        "idle_seconds": max(0, int((now - call.updated_at).total_seconds())),
        "charge_amount": _amount_text(call.charge_amount),
        "error_message": call.error_message,
        "has_late_usage": call.late_usage is not None,
        "late_usage_at": _iso(call.late_usage_at),
        "resolution": call.resolution,
        "allowed_actions": text_allowed_actions(call, now),
        "last_action": _last_action(session, "text_call", str(call.id)),
    }


def _task_response(task: Task, action: AdminAction) -> dict:
    return {
        "id": str(task.task_id),
        "status": task.status,
        "billing_status": task.billing_status,
        "resolution": task.resolution,
        "resolved_at": _iso(task.resolved_at),
        "audit_id": action.id,
        "credit_entry_id": action.credit_entry_id,
    }


def _text_response(call: TextCall, action: AdminAction) -> dict:
    return {
        "id": str(call.id),
        "status": call.status,
        "charge_amount": _amount_text(call.charge_amount),
        "resolution": call.resolution,
        "resolved_at": _iso(call.resolved_at),
        "audit_id": action.id,
        "credit_entry_id": action.credit_entry_id,
    }


def write_admin_action(
    session: Session,
    *,
    actor_id: int,
    action: str,
    target_type: str,
    target_id: str,
    request_id: UUID,
    fingerprint: str,
    reason: str,
    amount: Decimal | None,
    before: dict,
    after: dict,
    credit_entry_id: int | None = None,
) -> AdminAction:
    record = AdminAction(
        actor_user_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        request_fingerprint=fingerprint,
        reason=reason,
        amount=amount,
        credit_entry_id=credit_entry_id,
        before_snapshot=before,
        after_snapshot=after,
    )
    session.add(record)
    session.flush()
    return record


def _existing_action(session: Session, request_id: UUID) -> AdminAction | None:
    return session.scalar(select(AdminAction).where(AdminAction.request_id == request_id))


def ensure_replay(existing: AdminAction, actor_id: int, fingerprint: str) -> None:
    if existing.actor_user_id != actor_id or existing.request_fingerprint != fingerprint:
        raise HTTPException(409, "重复请求参数不一致")


def _task_exception_condition(now: datetime):
    return or_(
        Task.status == "submission_unknown",
        Task.review_required.is_(True),
        and_(
            Task.status.in_(["queued", "submitting", "pending", "processing"]),
            Task.updated_at <= now - TASK_ACTIVE_IDLE,
        ),
        and_(
            Task.status == "transferring",
            Task.updated_at <= now - TASK_TRANSFER_IDLE,
        ),
    )


def _text_exception_condition(now: datetime):
    return or_(
        TextCall.status == "usage_unknown",
        and_(
            TextCall.status == "processing",
            TextCall.updated_at <= now - TEXT_ACTIVE_IDLE,
        ),
    )


def exception_summary(session: Session) -> dict:
    now = datetime.now(UTC)
    text_conditions = _text_exception_condition(now)
    oldest_task = session.scalar(
        select(func.min(Task.created_at)).where(_task_exception_condition(now))
    )
    oldest_text = session.scalar(select(func.min(TextCall.created_at)).where(text_conditions))
    candidates = [value for value in (oldest_task, oldest_text) if value is not None]
    oldest = min(candidates) if candidates else None

    def count(model, *conditions) -> int:
        return session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

    return {
        "tasks": {
            "submission_unknown": count(Task, Task.status == "submission_unknown"),
            "stuck_queued": count(
                Task,
                Task.status == "queued",
                Task.updated_at <= now - TASK_ACTIVE_IDLE,
            ),
            "stuck_submitting": count(
                Task,
                Task.status == "submitting",
                Task.updated_at <= now - TASK_ACTIVE_IDLE,
            ),
            "stuck_processing": count(
                Task,
                Task.status.in_(["pending", "processing"]),
                Task.updated_at <= now - TASK_ACTIVE_IDLE,
            ),
            "stuck_transferring": count(
                Task,
                Task.status == "transferring",
                Task.updated_at <= now - TASK_TRANSFER_IDLE,
            ),
            "review_required": count(Task, Task.review_required.is_(True)),
        },
        "text_calls": {
            "usage_unknown": count(TextCall, TextCall.status == "usage_unknown"),
            "stuck_processing": count(
                TextCall,
                TextCall.status == "processing",
                TextCall.updated_at <= now - TEXT_ACTIVE_IDLE,
            ),
            "late_usage": count(TextCall, TextCall.late_usage.is_not(None)),
        },
        "oldest_waiting_seconds": (
            max(0, int((now - oldest).total_seconds())) if oldest is not None else 0
        ),
    }


def list_exception_tasks(
    session: Session,
    *,
    status: str | None = None,
    review_required: bool | None = None,
    min_idle_minutes: int | None = None,
    min_age_minutes: int | None = None,
    user_id: int | None = None,
    task_id: UUID | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict:
    now = datetime.now(UTC)
    conditions = [Task.status == status] if status else [_task_exception_condition(now)]
    if review_required is not None:
        conditions.append(Task.review_required.is_(review_required))
    if min_idle_minutes is not None:
        conditions.append(Task.updated_at <= now - timedelta(minutes=min_idle_minutes))
    if min_age_minutes is not None:
        conditions.append(Task.created_at <= now - timedelta(minutes=min_age_minutes))
    if user_id is not None:
        conditions.append(Task.user_id == user_id)
    if task_id is not None:
        conditions.append(Task.task_id == task_id)
    rows = session.execute(
        select(Task, User.email)
        .join(User, User.id == Task.user_id)
        .where(*conditions)
        .order_by(Task.created_at.asc())
        .offset(offset)
        .limit(limit)
    ).all()
    total = session.scalar(select(func.count()).select_from(Task).where(*conditions))
    return {
        "data": [_task_item(session, task, email, now) for task, email in rows],
        "total": total or 0,
    }


def list_exception_text_calls(
    session: Session,
    *,
    status: str | None = None,
    min_idle_minutes: int | None = None,
    min_age_minutes: int | None = None,
    user_id: int | None = None,
    call_id: UUID | None = None,
    has_late_usage: bool | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict:
    now = datetime.now(UTC)
    conditions = [TextCall.status == status] if status else [_text_exception_condition(now)]
    if min_idle_minutes is not None:
        conditions.append(TextCall.updated_at <= now - timedelta(minutes=min_idle_minutes))
    if min_age_minutes is not None:
        conditions.append(TextCall.created_at <= now - timedelta(minutes=min_age_minutes))
    if user_id is not None:
        conditions.append(TextCall.user_id == user_id)
    if call_id is not None:
        conditions.append(TextCall.id == call_id)
    if has_late_usage is not None:
        conditions.append(
            TextCall.late_usage.is_not(None) if has_late_usage else TextCall.late_usage.is_(None)
        )
    rows = session.execute(
        select(TextCall, User.email, CreditAccount.available)
        .join(User, User.id == TextCall.user_id)
        .join(CreditAccount, CreditAccount.user_id == TextCall.user_id)
        .where(*conditions)
        .order_by(TextCall.created_at.asc())
        .offset(offset)
        .limit(limit)
    ).all()
    total = session.scalar(select(func.count()).select_from(TextCall).where(*conditions))
    return {
        "data": [
            _text_item(session, call, email, available, now) for call, email, available in rows
        ],
        "total": total or 0,
    }


def _lock_account(session: Session, user_id: int) -> CreditAccount:
    account = session.scalar(
        select(CreditAccount).where(CreditAccount.user_id == user_id).with_for_update()
    )
    if account is None:
        raise HTTPException(409, "积分账户不存在")
    return account


def resolve_task(
    session: Session,
    admin_id: int,
    task_id: UUID,
    payload: TaskResolveRequest,
) -> dict:
    target_id = str(task_id)
    fingerprint = request_fingerprint(payload.action, "task", target_id, None, payload.reason)
    existing = _existing_action(session, payload.request_id)
    if existing is not None:
        ensure_replay(existing, admin_id, fingerprint)
        task = session.scalar(select(Task).where(Task.task_id == task_id))
        if task is None:
            raise HTTPException(404, "任务不存在")
        return _task_response(task, existing)

    task = _lock_nowait(
        session,
        select(Task).where(Task.task_id == task_id).with_for_update(nowait=True),
    )
    if task is None:
        raise HTTPException(404, "任务不存在")
    now = datetime.now(UTC)
    before = _snapshot_task(task)
    ready_result = _has_ready_result(session, task.id)
    if payload.action not in task_allowed_actions(task, ready_result):
        raise HTTPException(409, "当前状态不允许该操作")

    credit_entry_id: int | None = None
    amount: Decimal | None = None
    if payload.action == "retry_submit":
        task.next_run_at = now
        task.review_required = False
        task.error_code = None
        task.error_message = None
        task.resolution = "manual_requeued"
    elif payload.action == "requery":
        if task.status == "submission_unknown":
            if not task.upstream_task_id:
                raise HTTPException(409, "任务缺少上游 ID，无法重新查询")
            task.status = "pending"
        task.next_run_at = now
        task.review_required = False
        task.resolution = "manual_requeued"
    elif payload.action == "retry_transfer":
        task.next_run_at = now
        task.review_required = False
        task.resolution = "manual_retry_transfer"
    else:
        account = _lock_account(session, task.user_id)
        amount = task.frozen_amount
        account.available += amount
        account.frozen -= amount
        task.status = "failed"
        task.billing_status = "released"
        task.completed_at = now
        task.next_run_at = None
        task.error_code = "manual_release"
        task.error_message = "任务已关闭，冻结积分已释放"
        task.review_required = False
        task.result_snapshot = []
        task.resolution = "manual_released"
        if task.deadline_at and now >= task.deadline_at and task.timed_out_at is None:
            task.timed_out_at = now
        entry = CreditEntry(
            user_id=task.user_id,
            task_id=task.id,
            entry_type="release",
            idempotency_key=f"task:{task.task_id}:manual-release:{payload.request_id}",
            amount=amount,
            available_delta=amount,
            frozen_delta=-amount,
            description="人工核实关闭任务，释放冻结积分",
        )
        session.add(entry)
        session.flush()
        credit_entry_id = entry.id

    task.resolved_at = now
    task.resolved_by_user_id = admin_id
    after = _snapshot_task(task)
    try:
        action = write_admin_action(
            session,
            actor_id=admin_id,
            action=f"task.{payload.action}",
            target_type="task",
            target_id=target_id,
            request_id=payload.request_id,
            fingerprint=fingerprint,
            reason=payload.reason,
            amount=amount,
            before=before,
            after=after,
            credit_entry_id=credit_entry_id,
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _existing_action(session, payload.request_id)
        if existing is not None:
            ensure_replay(existing, admin_id, fingerprint)
            task = session.scalar(select(Task).where(Task.task_id == task_id))
            if task is not None:
                return _task_response(task, existing)
        raise
    session.refresh(task)
    return _task_response(task, action)


def resolve_text_call(
    session: Session,
    admin_id: int,
    call_id: UUID,
    payload: TextResolveRequest,
) -> dict:
    amount = (
        money(payload.amount)
        if payload.action == "manual_charge" and payload.amount is not None
        else None
    )
    target_id = str(call_id)
    fingerprint = request_fingerprint(
        payload.action, "text_call", target_id, amount, payload.reason
    )
    existing = _existing_action(session, payload.request_id)
    if existing is not None:
        ensure_replay(existing, admin_id, fingerprint)
        call = session.get(TextCall, call_id)
        if call is None:
            raise HTTPException(404, "调用不存在")
        return _text_response(call, existing)

    call = _lock_nowait(
        session,
        select(TextCall).where(TextCall.id == call_id).with_for_update(nowait=True),
    )
    if call is None:
        raise HTTPException(404, "调用不存在")
    now = datetime.now(UTC)
    before = _snapshot_text(call)
    if payload.action not in text_allowed_actions(call, now):
        raise HTTPException(409, "当前状态不允许该操作")

    credit_entry_id: int | None = None
    if payload.action == "mark_unknown":
        call.status = "usage_unknown"
        call.completed_at = now
        call.error_message = "调用已中断，用量待核实"
        call.resolution = "manual_marked_unknown"
    elif payload.action == "manual_charge":
        assert amount is not None
        account = _lock_account(session, call.user_id)
        account.available -= amount
        call.status = "settled_manually"
        call.charge_amount = amount
        call.cost_amount = None
        call.completed_at = call.completed_at or now
        call.error_message = "调用已人工核定"
        call.resolution = "manual_charged"
        entry = CreditEntry(
            user_id=call.user_id,
            entry_type="text_charge",
            idempotency_key=f"text:{call.id}:manual-charge:{payload.request_id}",
            amount=amount,
            available_delta=-amount,
            frozen_delta=Decimal(0),
            description="文本调用人工核定扣费",
        )
        session.add(entry)
        session.flush()
        credit_entry_id = entry.id
    else:
        call.status = "closed_no_charge"
        call.charge_amount = Decimal("0.00000000")
        call.cost_amount = None
        call.completed_at = call.completed_at or now
        call.error_message = "调用已关闭，未扣费"
        call.resolution = "manual_closed_no_charge"

    call.resolved_at = now
    call.resolved_by_user_id = admin_id
    after = _snapshot_text(call)
    try:
        action = write_admin_action(
            session,
            actor_id=admin_id,
            action=f"text.{payload.action}",
            target_type="text_call",
            target_id=target_id,
            request_id=payload.request_id,
            fingerprint=fingerprint,
            reason=payload.reason,
            amount=amount,
            before=before,
            after=after,
            credit_entry_id=credit_entry_id,
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _existing_action(session, payload.request_id)
        if existing is not None:
            ensure_replay(existing, admin_id, fingerprint)
            call = session.get(TextCall, call_id)
            if call is not None:
                return _text_response(call, existing)
        raise
    session.refresh(call)
    return _text_response(call, action)


def _audit_item(
    action: AdminAction,
    email: str,
    *,
    include_snapshots: bool = False,
) -> dict:
    data = {
        "id": action.id,
        "actor": {"id": action.actor_user_id, "email": email},
        "action": action.action,
        "target_type": action.target_type,
        "target_id": action.target_id,
        "amount": _amount_text(action.amount),
        "reason": action.reason,
        "credit_entry_id": action.credit_entry_id,
        "created_at": _iso(action.created_at),
    }
    if include_snapshots:
        data["before_snapshot"] = action.before_snapshot
        data["after_snapshot"] = action.after_snapshot
    return data


def list_audit_actions(
    session: Session,
    *,
    actor_user_id: int | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    created_from: int | None = None,
    created_to: int | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict:
    conditions = []
    if actor_user_id is not None:
        conditions.append(AdminAction.actor_user_id == actor_user_id)
    if action is not None:
        conditions.append(AdminAction.action == action)
    if target_type is not None:
        conditions.append(AdminAction.target_type == target_type)
    if target_id is not None:
        conditions.append(AdminAction.target_id == target_id)
    if created_from is not None:
        conditions.append(func.extract("epoch", AdminAction.created_at) >= created_from)
    if created_to is not None:
        conditions.append(func.extract("epoch", AdminAction.created_at) < created_to)
    rows = session.execute(
        select(AdminAction, User.email)
        .join(User, User.id == AdminAction.actor_user_id)
        .where(*conditions)
        .order_by(AdminAction.created_at.desc(), AdminAction.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    total = session.scalar(select(func.count()).select_from(AdminAction).where(*conditions))
    return {
        "data": [_audit_item(action, email) for action, email in rows],
        "total": total or 0,
    }


def get_audit_action(session: Session, action_id: int) -> dict:
    row = session.execute(
        select(AdminAction, User.email)
        .join(User, User.id == AdminAction.actor_user_id)
        .where(AdminAction.id == action_id)
    ).first()
    if row is None:
        raise HTTPException(404, "审计记录不存在")
    action, email = row
    return _audit_item(action, email, include_snapshots=True)
