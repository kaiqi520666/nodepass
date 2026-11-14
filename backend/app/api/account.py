from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import String, case, cast, func, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import CurrentUser, Database
from app.core.config import get_settings
from app.core.security import SESSION_COOKIE, issue_session
from app.models import CreditEntry, Task, TaskAsset, TextCall
from app.schemas import (
    Credentials,
    DailyConsumption,
    DashboardSummary,
    TaskSummary,
    TextCallDetail,
    TextCallPage,
    TextCallSummary,
    TextSalePrice,
    UserSummary,
)
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


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(user: CurrentUser, session: Database):
    today = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    amount = case(
        (CreditEntry.entry_type == "refund", -CreditEntry.amount), else_=CreditEntry.amount
    )
    consumed, today_consumed = session.execute(
        select(
            func.coalesce(func.sum(amount), 0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (CreditEntry.created_at >= today)
                            & (CreditEntry.created_at < today + timedelta(days=1)),
                            amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(
            CreditEntry.user_id == user.id,
            CreditEntry.entry_type.in_(["settle", "text_charge", "refund"]),
        )
    ).one()
    start = today - timedelta(days=6)
    day = func.date(func.timezone("Asia/Shanghai", CreditEntry.created_at))
    daily = dict(
        session.execute(
            select(day, func.coalesce(func.sum(amount), 0))
            .where(
                CreditEntry.user_id == user.id,
                CreditEntry.entry_type.in_(["settle", "text_charge", "refund"]),
                CreditEntry.created_at >= start,
            )
            .group_by(day)
        ).all()
    )
    trend = [
        DailyConsumption(
            date=(start + timedelta(days=offset)).date().isoformat(),
            consumed=daily.get((start + timedelta(days=offset)).date(), Decimal("0")),
        )
        for offset in range(7)
    ]
    requests = session.scalar(
        select(func.count()).select_from(Task).where(Task.user_id == user.id)
    ) + session.scalar(
        select(func.count()).select_from(TextCall).where(TextCall.user_id == user.id)
    )
    return DashboardSummary(
        available=user.account.available,
        consumed=consumed,
        requests=requests,
        today_consumed=today_consumed,
        trend=trend,
    )


def _text_call_summary(call: TextCall) -> TextCallSummary:
    usage = call.usage
    return TextCallSummary(
        id=call.id,
        model=call.price_snapshot["public_id"],
        status=call.status,
        created=int(call.created_at.timestamp()),
        completed=int(call.completed_at.timestamp()) if call.completed_at else None,
        duration_ms=max(
            0,
            int(
                ((call.completed_at or datetime.now(UTC)) - call.created_at).total_seconds() * 1000
            ),
        ),
        input_tokens=usage["input_tokens"] if usage is not None else None,
        output_tokens=usage["output_tokens"] if usage is not None else None,
        charge_amount=call.charge_amount,
    )


@router.get("/text-calls", response_model=TextCallPage)
def list_text_calls(
    user: CurrentUser,
    session: Database,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    query: str = "",
    model: str | None = None,
    status: (
        Literal[
            "processing",
            "succeeded",
            "failed",
            "usage_unknown",
            "settled_manually",
            "closed_no_charge",
        ]
        | None
    ) = None,
    created_from: int | None = Query(default=None, ge=0),
    created_to: int | None = Query(default=None, ge=0),
):
    if created_from is not None and created_to is not None and created_from >= created_to:
        raise HTTPException(422, "结束日期必须晚于开始日期")
    conditions = [TextCall.user_id == user.id]
    if query.strip():
        conditions.append(cast(TextCall.id, String).icontains(query.strip(), autoescape=True))
    if model is not None:
        conditions.append(TextCall.price_snapshot["public_id"].astext == model)
    if status is not None:
        conditions.append(TextCall.status == status)
    if created_from is not None:
        conditions.append(func.extract("epoch", TextCall.created_at) >= created_from)
    if created_to is not None:
        conditions.append(func.extract("epoch", TextCall.created_at) < created_to)
    calls = session.scalars(
        select(TextCall)
        .where(*conditions)
        .order_by(TextCall.created_at.desc(), TextCall.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    model_ids = TextCall.price_snapshot["public_id"].astext
    return TextCallPage(
        data=[_text_call_summary(call) for call in calls],
        total=session.scalar(select(func.count()).select_from(TextCall).where(*conditions)),
        models=session.scalars(
            select(model_ids).where(TextCall.user_id == user.id).distinct().order_by(model_ids)
        ).all(),
    )


@router.get("/text-calls/{call_id}", response_model=TextCallDetail)
def get_text_call(call_id: UUID, user: CurrentUser, session: Database):
    call = session.scalar(
        select(TextCall).where(TextCall.id == call_id, TextCall.user_id == user.id)
    )
    if call is None:
        raise HTTPException(404, "调用记录不存在")
    return TextCallDetail(
        **_text_call_summary(call).model_dump(),
        endpoint=f"/v1/{call.endpoint}",
        stream=call.price_snapshot.get("stream"),
        usage=call.usage,
        sale_price=TextSalePrice.model_validate(call.price_snapshot),
        error_message=call.error_message,
    )


def _task_summary(task: Task, links: list[TaskAsset]) -> TaskSummary:
    data = []
    for link in sorted(links, key=lambda item: item.position):
        asset = link.asset
        if task.status == "succeeded" and asset and asset.status == "ready" and asset.public_url:
            data.append({"url": asset.public_url})
    completed = task.completed_at
    duration_ms = (
        max(0, int(((completed or datetime.now(UTC)) - task.created_at).total_seconds() * 1000))
        if task.created_at
        else None
    )
    return TaskSummary(
        id=task.task_id,
        object=f"{task.model_snapshot['media_type']}.generation",
        status=task.status,
        model=task.model_snapshot.get("public_id", ""),
        model_name=task.model_snapshot["display_name"],
        media_type=task.model_snapshot["media_type"],
        created=int(task.created_at.timestamp()),
        billing_status=task.billing_status,
        frozen_amount=task.frozen_amount,
        consumed_amount=task.frozen_amount
        if task.billing_status == "settled"
        else Decimal("0.00000000"),
        completed=int(completed.timestamp()) if completed else None,
        duration_ms=duration_ms,
        timed_out=task.has_timed_out(datetime.now(UTC)),
        request_params=task.request_params,
        upstream_status=task.upstream_status,
        error_message=task.error_message,
        resolution=task.resolution,
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
