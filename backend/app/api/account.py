from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.dependencies import CurrentUser, Database
from app.core.config import get_settings
from app.core.security import SESSION_COOKIE, issue_session
from app.models import Task, TaskAsset
from app.schemas import Credentials, TaskSummary, UserSummary
from app.services.accounts import authenticate, register

router = APIRouter(prefix="/api/account", tags=["account"], include_in_schema=False)


def set_session(response: Response, user_id: int) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(user_id),
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api",
    )


@router.post("/register", response_model=UserSummary, status_code=201)
def register_account(data: Credentials, session: Database, response: Response):
    user = register(session, data)
    set_session(response, user.id)
    return user


@router.post("/login", response_model=UserSummary)
def login(data: Credentials, session: Database, response: Response):
    user = authenticate(session, data)
    set_session(response, user.id)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/api", samesite="strict")


@router.get("/me", response_model=UserSummary)
def me(user: CurrentUser):
    return user


def _task_summary(task: Task, links: list[TaskAsset]) -> TaskSummary:
    data = []
    for link in sorted(links, key=lambda item: item.position):
        asset = link.asset
        if asset and asset.status == "ready" and asset.public_url:
            data.append({"url": asset.public_url})
    completed = task.completed_at
    duration_ms = (
        max(0, int(((completed or datetime.now(UTC)) - task.created_at).total_seconds() * 1000))
        if task.created_at
        else None
    )
    return TaskSummary(
        id=task.task_id,
        status=task.status,
        model=task.model_snapshot.get("public_id", ""),
        model_name=task.model_snapshot["display_name"],
        media_type=task.model_snapshot["media_type"],
        created=int(task.created_at.timestamp()),
        billing_status=task.billing_status,
        frozen_amount=task.frozen_amount,
        consumed_amount=task.frozen_amount
        if task.billing_status == "settled"
        else Decimal("0.0000"),
        completed=int(completed.timestamp()) if completed else None,
        duration_ms=duration_ms,
        timed_out=task.timed_out_at is not None,
        request_params=task.request_params,
        upstream_status=task.upstream_status,
        error_message=task.error_message,
        data=data,
    )


@router.get("/tasks", response_model=dict[str, list[TaskSummary]])
def list_tasks(user: CurrentUser, session: Database):
    tasks = (
        session.scalars(
            select(Task)
            .options(joinedload(Task.task_assets).joinedload(TaskAsset.asset))
            .where(Task.user_id == user.id)
            .order_by(Task.created_at.desc())
            .limit(100)
        )
        .unique()
        .all()
    )
    return {"data": [_task_summary(task, task.task_assets) for task in tasks]}


@router.get("/tasks/{task_id}", response_model=TaskSummary)
def get_task(task_id: UUID, user: CurrentUser, session: Database):
    task = session.scalar(
        select(Task)
        .options(joinedload(Task.task_assets).joinedload(TaskAsset.asset))
        .where(Task.task_id == task_id, Task.user_id == user.id)
    )
    if task is None:
        raise HTTPException(404, "任务不存在")
    return _task_summary(task, task.task_assets)
