from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import credential_cipher
from app.models import Asset, CreditAccount, CreditEntry, Provider, Task, TaskAsset
from app.providers import CangyuanImageAdapter, ProviderError
from app.providers.cangyuan import ImageOutput, decode_output
from app.services.storage import upload_result


def _adapter(provider: Provider) -> CangyuanImageAdapter:
    try:
        api_key = (
            credential_cipher()
            .decrypt(provider.credentials_encrypted.encode("ascii"))
            .decode("utf-8")
        )
    except (HTTPException, ValueError, TypeError) as exc:
        raise ProviderError("供应商凭证无法解密", explicit_failure=True) from exc
    if provider.adapter_key != "cangyuan_image":
        raise ProviderError("当前供应商适配器不支持图片生成", explicit_failure=True)
    return CangyuanImageAdapter(provider, api_key)


def _poll_at(task: Task, now: datetime) -> datetime:
    seconds = int(
        (task.provider_snapshot or {}).get("request_config", {}).get("poll_interval_seconds", 5)
    )
    return now + timedelta(seconds=max(5, min(seconds, 60)))


def _record_error(task: Task, message: str, now: datetime, *, review: bool = False) -> None:
    task.error_code = "provider_error"
    task.error_message = message[:500]
    task.next_run_at = _poll_at(task, now)
    task.review_required = task.review_required or review
    if task.deadline_at and now >= task.deadline_at and task.timed_out_at is None:
        task.timed_out_at = now


def _release(session: Session, task_id: int, message: str) -> None:
    task = session.scalar(select(Task).where(Task.id == task_id).with_for_update())
    if task is None or task.billing_status != "held":
        return
    account = session.scalar(
        select(CreditAccount).where(CreditAccount.user_id == task.user_id).with_for_update()
    )
    if account is None:
        raise RuntimeError("积分账户不存在")
    account.available += task.frozen_amount
    account.frozen -= task.frozen_amount
    task.status = "failed"
    task.billing_status = "released"
    task.error_code = "provider_rejected"
    task.error_message = message[:500]
    task.completed_at = datetime.now(UTC)
    task.next_run_at = None
    session.add(
        CreditEntry(
            user_id=task.user_id,
            task_id=task.id,
            entry_type="release",
            idempotency_key=f"task:{task.task_id}:release",
            amount=task.frozen_amount,
            available_delta=task.frozen_amount,
            frozen_delta=-task.frozen_amount,
            description="图片生成明确失败，释放冻结积分",
        )
    )
    session.commit()


def _settle(
    session: Session,
    task_id: int,
    assets: Iterable[Asset],
) -> None:
    task = session.scalar(select(Task).where(Task.id == task_id).with_for_update())
    if task is None or task.billing_status != "held":
        return
    account = session.scalar(
        select(CreditAccount).where(CreditAccount.user_id == task.user_id).with_for_update()
    )
    if account is None:
        raise RuntimeError("积分账户不存在")
    existing = session.scalar(
        select(TaskAsset).where(TaskAsset.task_id == task.id, TaskAsset.role == "result")
    )
    if existing is None:
        for position, asset in enumerate(assets):
            session.add(
                TaskAsset(task_id=task.id, role="result", position=position, asset_id=asset.id)
            )
    session.flush()
    account.frozen -= task.frozen_amount
    task.status = "succeeded"
    task.billing_status = "settled"
    task.completed_at = datetime.now(UTC)
    task.next_run_at = None
    session.add(
        CreditEntry(
            user_id=task.user_id,
            task_id=task.id,
            entry_type="settle",
            idempotency_key=f"task:{task.task_id}:settle",
            amount=task.frozen_amount,
            available_delta=0,
            frozen_delta=-task.frozen_amount,
            description="图片结果已转存 OSS，完成积分结算",
        )
    )
    session.commit()


def _transfer_and_settle(session: Session, task: Task, outputs: tuple[ImageOutput, ...]) -> None:
    existing = session.scalars(
        select(TaskAsset)
        .where(TaskAsset.task_id == task.id, TaskAsset.role == "result")
        .order_by(TaskAsset.position)
    ).all()
    if existing:
        assets = [session.get(Asset, link.asset_id) for link in existing]
        if all(asset and asset.status == "ready" for asset in assets):
            _settle(session, task.id, [asset for asset in assets if asset])
            return
    if len(outputs) != task.quantity:
        raise ProviderError("上游返回结果数量不符合本站要求")
    assets: list[Asset] = []
    for position, output in enumerate(outputs):
        content, content_type = decode_output(output)
        stored = upload_result(session, str(task.task_id), position, content, content_type)
        asset = Asset(
            user_id=task.user_id,
            source_kind="generated",
            status="ready",
            oss_region=str(stored["region"]),
            oss_bucket=str(stored["bucket"]),
            oss_object_key=str(stored["object_key"]),
            public_url=str(stored["public_url"]),
            content_type=str(stored["content_type"]),
            byte_size=int(stored["byte_size"]),
            checksum=None,
            ready_at=datetime.now(UTC),
        )
        session.add(asset)
        session.flush()
        assets.append(asset)
    _settle(session, task.id, assets)


def process_task(session: Session, task: Task) -> None:
    now = datetime.now(UTC)
    provider = session.get(Provider, task.provider_id)
    if provider is None:
        _release(session, task.id, "供应商不存在")
        return
    if task.status == "submitting":
        task.status = "submission_unknown"
        task.review_required = True
        _record_error(task, "上次提交中断，等待核实上游是否已受理", now, review=True)
        session.commit()
        return
    try:
        adapter = _adapter(provider)
        if task.status == "queued":
            task.status = "submitting"
            session.commit()
            result = adapter.submit(task)
            task.upstream_task_id = result.upstream_id
            task.submitted_at = now
        elif task.upstream_task_id:
            result = adapter.query(task.upstream_task_id)
        else:
            _record_error(task, "缺少上游任务 ID，无法继续查询", now, review=True)
            session.commit()
            return
    except ProviderError as exc:
        if task.status == "submitting" and exc.explicit_failure:
            _release(session, task.id, str(exc))
        else:
            _record_error(task, str(exc), now, review=task.status == "submitting")
            if task.status == "submitting":
                task.status = "submission_unknown"
            session.commit()
        return

    task.upstream_status = result.raw_status
    if result.state == "failed":
        _release(session, task.id, result.error or "上游明确返回失败")
        return
    if result.state == "succeeded":
        task.status = "transferring"
        task.upstream_completed_at = now
        task.next_run_at = now
        session.commit()
        try:
            _transfer_and_settle(session, task, result.outputs)
        except (HTTPException, ProviderError, OSError, RuntimeError) as exc:
            session.rollback()
            task = session.get(Task, task.id)
            if task:
                task.status = "transferring"
                _record_error(task, str(exc), now)
                session.commit()
        return
    task.status = "pending" if result.state == "pending" else "processing"
    task.next_run_at = _poll_at(task, now)
    if task.deadline_at and now >= task.deadline_at and task.timed_out_at is None:
        task.timed_out_at = now
    session.commit()


def process_next_task(session: Session) -> bool:
    now = datetime.now(UTC)
    task = session.scalar(
        select(Task)
        .where(
            Task.status.in_(
                [
                    "queued",
                    "submitting",
                    "pending",
                    "processing",
                    "transferring",
                ]
            ),
            or_(Task.next_run_at.is_(None), Task.next_run_at <= now),
        )
        .order_by(Task.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if task is None:
        return False
    process_task(session, task)
    return True
