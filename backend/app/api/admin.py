from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import AdminUser, Database
from app.core.security import password_hash
from app.models import CreditAccount, CreditEntry, Model, Provider, SystemSetting, User
from app.schemas import (
    AdminPasswordUpdate,
    CreditAdjustment,
    OssSettingsInput,
    OssSettingsSummary,
    OssTestResult,
    UserSummary,
)
from app.schemas_catalog import ModelInput, ProviderInput, ProviderSummary
from app.services.catalog_admin import (
    image_profiles,
    model_summary,
    provider_summary,
    save_model,
    save_provider,
)
from app.services.settings import oss_summary, save_oss_settings, test_oss_connection

router = APIRouter(prefix="/api/admin", include_in_schema=False)


@router.get("/users")
def list_users(
    admin: AdminUser,
    session: Database,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    users = session.scalars(
        select(User)
        .options(joinedload(User.account))
        .order_by(User.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "data": [UserSummary.model_validate(user) for user in users],
        "total": session.scalar(select(func.count()).select_from(User)),
    }


@router.post("/users/{user_id}/credits", response_model=UserSummary)
def adjust_user_credits(
    user_id: int,
    payload: CreditAdjustment,
    admin: AdminUser,
    session: Database,
):
    user = session.scalar(select(User).options(joinedload(User.account)).where(User.id == user_id))
    if user is None or user.account is None:
        raise HTTPException(404, "用户不存在")
    amount = payload.amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise HTTPException(422, "积分必须大于 0.0000")
    account = session.scalar(
        select(CreditAccount).where(CreditAccount.user_id == user.id).with_for_update()
    )
    if account is None:
        raise HTTPException(404, "积分账户不存在")
    available_delta = amount if payload.direction == "increase" else -amount
    if payload.direction == "decrease" and account.available < amount:
        raise HTTPException(409, "可用积分不足")
    account.available += available_delta
    session.add(
        CreditEntry(
            user_id=user.id,
            entry_type="admin_credit" if payload.direction == "increase" else "admin_debit",
            idempotency_key=f"admin:{admin.id}:user:{user.id}:{uuid4()}",
            amount=amount,
            available_delta=available_delta,
            frozen_delta=Decimal("0.0000"),
            description=payload.reason,
        )
    )
    session.commit()
    session.refresh(user)
    return user


@router.post("/users/{user_id}/password", response_model=UserSummary)
def update_user_password(
    user_id: int,
    payload: AdminPasswordUpdate,
    admin: AdminUser,
    session: Database,
):
    user = session.scalar(select(User).options(joinedload(User.account)).where(User.id == user_id))
    if user is None:
        raise HTTPException(404, "用户不存在")
    user.password_hash = password_hash.hash(payload.password.get_secret_value())
    session.commit()
    session.refresh(user)
    return user


@router.get("/providers", response_model=dict[str, list[ProviderSummary]])
def list_providers(admin: AdminUser, session: Database):
    return {
        "data": [
            provider_summary(row)
            for row in session.scalars(select(Provider).order_by(Provider.id.desc()))
        ]
    }


@router.post("/providers", response_model=ProviderSummary, status_code=201)
def create_provider(payload: ProviderInput, admin: AdminUser, session: Database):
    return save_provider(session, payload)


@router.put("/providers/{provider_id}", response_model=ProviderSummary)
def update_provider(provider_id: int, payload: ProviderInput, admin: AdminUser, session: Database):
    return save_provider(session, payload, provider_id)


@router.get("/image-options")
def image_options(admin: AdminUser):
    return {"data": image_profiles()}


@router.get("/models")
def list_managed_models(admin: AdminUser, session: Database):
    return {
        "data": [
            model_summary(row)
            for row in session.scalars(
                select(Model)
                .options(joinedload(Model.prices))
                .where(Model.media_type == "image")
                .order_by(Model.id.desc())
            ).unique()
        ]
    }


@router.post("/models", status_code=201)
def create_model(payload: ModelInput, admin: AdminUser, session: Database):
    return save_model(session, payload)


@router.put("/models/{model_id}")
def update_model(model_id: int, payload: ModelInput, admin: AdminUser, session: Database):
    return save_model(session, payload, model_id)


@router.get("/settings/oss", response_model=OssSettingsSummary)
def get_oss_settings(admin: AdminUser, session: Database):
    return oss_summary(session.get(SystemSetting, "oss"))


@router.put("/settings/oss", response_model=OssSettingsSummary)
def update_oss_settings(payload: OssSettingsInput, admin: AdminUser, session: Database):
    return save_oss_settings(session, payload)


@router.post("/settings/oss/test", response_model=OssTestResult)
def test_oss(admin: AdminUser, session: Database):
    return test_oss_connection(session)
