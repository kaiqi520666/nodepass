from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import AdminUser, Database
from app.schemas_admin import TaskResolveRequest, TextResolveRequest
from app.services import admin_operations

router = APIRouter(prefix="/api/admin", include_in_schema=False)


@router.get("/exceptions/summary")
def exception_summary(admin: AdminUser, session: Database):
    return admin_operations.exception_summary(session)


@router.get("/exceptions/tasks")
def list_exception_tasks(
    admin: AdminUser,
    session: Database,
    status: str | None = None,
    review_required: bool | None = None,
    min_idle_minutes: int | None = Query(None, ge=0),
    min_age_minutes: int | None = Query(None, ge=0),
    user_id: int | None = Query(None, ge=1),
    task_id: UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    return admin_operations.list_exception_tasks(
        session,
        status=status,
        review_required=review_required,
        min_idle_minutes=min_idle_minutes,
        min_age_minutes=min_age_minutes,
        user_id=user_id,
        task_id=task_id,
        offset=offset,
        limit=limit,
    )


@router.get("/exceptions/text-calls")
def list_exception_text_calls(
    admin: AdminUser,
    session: Database,
    status: str | None = None,
    min_idle_minutes: int | None = Query(None, ge=0),
    min_age_minutes: int | None = Query(None, ge=0),
    user_id: int | None = Query(None, ge=1),
    call_id: UUID | None = None,
    has_late_usage: bool | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    return admin_operations.list_exception_text_calls(
        session,
        status=status,
        min_idle_minutes=min_idle_minutes,
        min_age_minutes=min_age_minutes,
        user_id=user_id,
        call_id=call_id,
        has_late_usage=has_late_usage,
        offset=offset,
        limit=limit,
    )


@router.post("/tasks/{task_id}/resolve")
def resolve_task(
    task_id: UUID,
    payload: TaskResolveRequest,
    admin: AdminUser,
    session: Database,
):
    return admin_operations.resolve_task(session, admin.id, task_id, payload)


@router.post("/text-calls/{call_id}/resolve")
def resolve_text_call(
    call_id: UUID,
    payload: TextResolveRequest,
    admin: AdminUser,
    session: Database,
):
    return admin_operations.resolve_text_call(session, admin.id, call_id, payload)


@router.get("/audit-actions")
def list_audit_actions(
    admin: AdminUser,
    session: Database,
    actor_user_id: int | None = Query(None, ge=1),
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    created_from: int | None = Query(None, ge=0),
    created_to: int | None = Query(None, ge=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    return admin_operations.list_audit_actions(
        session,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        created_from=created_from,
        created_to=created_to,
        offset=offset,
        limit=limit,
    )


@router.get("/audit-actions/{action_id}")
def get_audit_action(action_id: int, admin: AdminUser, session: Database):
    return admin_operations.get_audit_action(session, action_id)
