import logging
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from http.client import HTTPException as TransportError

from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from oss2.exceptions import OssError
from sqlalchemy import or_, select
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import credential_cipher
from app.models import Asset, CreditAccount, CreditEntry, Provider, Task, TaskAsset
from app.providers import CangyuanImageAdapter, MeaiccVideoAdapter, ProviderError
from app.providers.base import GenerationOutput, JsonAdapter
from app.providers.cangyuan import decode_output
from app.services.storage import (
    StorageConfigurationError,
    upload_result,
    upload_video_result,
)

logger = logging.getLogger(__name__)


def _adapter(provider: Provider, task: Task) -> JsonAdapter:
    try:
        api_key = (
            credential_cipher()
            .decrypt(provider.credentials_encrypted.encode("ascii"))
            .decode("utf-8")
        )
    except (HTTPException, ValueError, TypeError, InvalidToken) as exc:
        raise ProviderError("供应商凭证无法解密", explicit_failure=True) from exc
    adapters = {"cangyuan_image": CangyuanImageAdapter, "meaicc_video": MeaiccVideoAdapter}
    adapter = adapters.get(task.provider_snapshot["adapter_key"])
    if adapter is None:
        raise ProviderError("供应商接入方式不受支持", explicit_failure=True)
    return adapter(task.provider_snapshot, api_key)


def _poll_at(task: Task, now: datetime) -> datetime:
    seconds = task.provider_snapshot["request_config"]["poll_interval_seconds"]
    return now + timedelta(seconds=seconds)


def _clear_transient_resolution(task: Task) -> None:
    if task.resolution in {"manual_requeued", "manual_retry_transfer"}:
        task.resolution = None
        task.resolved_at = None
        task.resolved_by_user_id = None


def _record_error(task: Task, message: str, now: datetime, *, review: bool = False) -> None:
    task.error_code = "provider_error"
    task.error_message = message[:500]
    task.next_run_at = None if review else _poll_at(task, now)
    task.review_required = task.review_required or review
    if task.deadline_at and now >= task.deadline_at and task.timed_out_at is None:
        task.timed_out_at = now


def _pause_task(task: Task, message: str, now: datetime) -> None:
    if task.status == "submitting":
        task.status = "submission_unknown"
    task.error_code = "review_required"
    task.error_message = message
    task.review_required = True
    task.next_run_at = None
    if task.deadline_at and now >= task.deadline_at and task.timed_out_at is None:
        task.timed_out_at = now
    logger.warning("task_paused task_id=%s status=%s", task.task_id, task.status)


def _task_state_token(task: Task) -> tuple:
    return (
        task.updated_at,
        task.status,
        task.billing_status,
        task.review_required,
        task.next_run_at,
        task.resolution,
        task.error_code,
        task.error_message,
    )


def _is_expected_submission_transition(state_token: tuple, task: Task) -> bool:
    return (
        state_token[1] == "queued"
        and task.status == "submitting"
        and task.billing_status == state_token[2]
        and not task.review_required
        and task.resolution == state_token[5]
        and task.upstream_task_id is None
        and task.submitted_at is None
    )


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
    _clear_transient_resolution(task)
    if task.has_timed_out(task.completed_at) and task.timed_out_at is None:
        task.timed_out_at = task.completed_at
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
            description="生成任务明确失败，释放冻结积分",
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
    if task.has_timed_out(task.completed_at) and task.timed_out_at is None:
        task.timed_out_at = task.completed_at
    task.error_code = None
    task.error_message = None
    task.review_required = False
    task.result_snapshot = []
    task.next_run_at = None
    _clear_transient_resolution(task)
    session.add(
        CreditEntry(
            user_id=task.user_id,
            task_id=task.id,
            entry_type="settle",
            idempotency_key=f"task:{task.task_id}:settle",
            amount=task.frozen_amount,
            available_delta=0,
            frozen_delta=-task.frozen_amount,
            description="生成结果已转存 OSS，完成积分结算",
        )
    )
    session.commit()


def _transfer_and_settle(session: Session, task: Task) -> None:
    if task.billing_status != "held":
        return
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
    if not isinstance(task.result_snapshot, list) or len(task.result_snapshot) != 1:
        raise ValueError("Invalid result snapshot")
    outputs = tuple(GenerationOutput(**item) for item in task.result_snapshot)
    for output in outputs:
        if (
            not isinstance(output.content_type, str)
            or not output.content_type.strip()
            or not (output.url or output.b64_json)
            or any(
                value is not None and (not isinstance(value, str) or not value.strip())
                for value in (output.url, output.b64_json)
            )
            or task.model_snapshot["media_type"] not in {"image", "video"}
            or (task.model_snapshot["media_type"] == "video" and not output.url)
        ):
            raise ValueError("Invalid result output")
    assets: list[Asset] = []
    for position, output in enumerate(outputs):
        if task.model_snapshot["media_type"] == "video":
            if not output.url:
                raise ProviderError("上游视频结果缺少地址")
            stored = upload_video_result(
                session,
                str(task.task_id),
                position,
                output.url,
                task.provider_snapshot["request_config"]["timeout_seconds"],
            )
        else:
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


def _process_task(session: Session, task: Task) -> None:
    if task.billing_status != "held" or task.status == "submission_unknown" or task.review_required:
        return
    now = datetime.now(UTC)
    if task.status == "transferring":
        state_token = _task_state_token(task)
        try:
            _transfer_and_settle(session, task)
        except StorageConfigurationError:
            task_id = task.id
            session.rollback()
            task = session.scalar(
                select(Task)
                .where(Task.id == task_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                task is None
                or task.billing_status != "held"
                or _task_state_token(task) != state_token
            ):
                return
            _pause_task(task, "OSS 配置或权限不可用，已暂停等待核实", datetime.now(UTC))
            session.commit()
            logger.warning(
                "task_transfer_paused task_id=%s reason=storage_configuration",
                task.task_id,
            )
        except (
            HTTPException,
            ProviderError,
            OSError,
            OssError,
            TransportError,
        ) as exc:
            if isinstance(exc, ProviderError) and exc.explicit_failure:
                raise
            task_id = task.id
            session.rollback()
            task = session.scalar(
                select(Task)
                .where(Task.id == task_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if task is None or task.billing_status != "held" or task.review_required:
                return
            if _task_state_token(task) != state_token:
                return
            _record_error(task, "结果转存暂时失败，将按任务间隔重试", datetime.now(UTC))
            session.commit()
            logger.warning(
                "task_transfer_retry task_id=%s error_type=%s",
                task.task_id,
                type(exc).__name__,
            )
        return
    if task.status == "submitting":
        _pause_task(task, "上次提交中断，等待核实上游是否已受理", now)
        session.commit()
        return
    if task.status == "queued" and (
        task.upstream_task_id or task.submitted_at or task.result_snapshot
    ):
        task.status = "submission_unknown"
        _pause_task(task, "排队任务存在执行记录，等待核实，禁止再次提交", now)
        session.commit()
        return
    provider = session.get(Provider, task.provider_id)
    if provider is None:
        _pause_task(task, "供应商不存在，已暂停等待核实", now)
        session.commit()
        return
    try:
        adapter = _adapter(provider, task)
    except ProviderError:
        _pause_task(task, "任务配置不可用，已暂停等待核实", now)
        session.commit()
        return
    try:
        if task.status == "queued":
            task.status = "submitting"
            session.commit()
            result = adapter.submit(task)
            task.upstream_task_id = result.upstream_id
            task.submitted_at = now
        elif task.upstream_task_id:
            result = adapter.query(task)
        else:
            _record_error(task, "缺少上游任务 ID，无法继续查询", now, review=True)
            session.commit()
            return
    except ProviderError as exc:
        if task.status == "submitting" and exc.explicit_failure:
            _release(session, task.id, str(exc))
        elif exc.explicit_failure:
            _pause_task(task, "上游查询被拒绝，已暂停等待核实", datetime.now(UTC))
            session.commit()
        else:
            _record_error(task, str(exc), datetime.now(UTC), review=task.status == "submitting")
            if task.status == "submitting":
                task.status = "submission_unknown"
            session.commit()
        logger.warning(
            "task_provider_error task_id=%s status=%s explicit_failure=%s",
            task.task_id,
            task.status,
            exc.explicit_failure,
        )
        return

    now = datetime.now(UTC)
    task.upstream_status = result.raw_status[:64] if result.raw_status else None
    if result.state == "failed":
        _release(session, task.id, result.error or "上游明确返回失败")
        return
    if result.state == "succeeded":
        task.status = "transferring"
        task.upstream_completed_at = now
        task.result_snapshot = [asdict(output) for output in result.outputs]
        task.next_run_at = now
        session.commit()
        # Transfer on the next worker turn so the task row lock covers the upload.
        return
    task.status = "pending" if result.state == "pending" else "processing"
    task.next_run_at = _poll_at(task, now)
    if task.deadline_at and now >= task.deadline_at and task.timed_out_at is None:
        task.timed_out_at = now
    session.commit()


def process_task(session: Session, task: Task) -> None:
    task_id = task.id
    state_token = _task_state_token(task)
    try:
        _process_task(session, task)
    except Exception as exc:
        # A rejected row is task-local; infrastructure failures belong to the worker retry loop.
        if isinstance(exc, SQLAlchemyError) and not isinstance(exc, (DataError, IntegrityError)):
            raise
        session.rollback()
        task = session.scalar(
            select(Task)
            .where(Task.id == task_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            task is None
            or task.billing_status != "held"
            or (
                _task_state_token(task) != state_token
                and not _is_expected_submission_transition(state_token, task)
            )
        ):
            return
        logger.error(
            "task_execution_error task_id=%s status=%s error_type=%s",
            task.task_id,
            task.status,
            type(exc).__name__,
        )
        _pause_task(task, "任务执行异常，已暂停等待核实", datetime.now(UTC))
        session.commit()


def process_next_task(session: Session) -> bool:
    now = datetime.now(UTC)
    task = session.scalar(
        select(Task)
        .where(
            Task.billing_status == "held",
            Task.review_required.is_(False),
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
