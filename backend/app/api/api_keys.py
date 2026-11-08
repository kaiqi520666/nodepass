from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.dependencies import CurrentUser, Database
from app.core.security import credential_cipher, digest_api_key, issue_api_key
from app.models import ApiKey
from app.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeySecret, ApiKeySummary, ApiKeyUpdate

router = APIRouter(prefix="/api/account/keys", tags=["account"], include_in_schema=False)


@router.get("", response_model=dict[str, list[ApiKeySummary]])
def list_keys(user: CurrentUser, session: Database):
    return {
        "data": session.scalars(
            select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.id.desc())
        ).all()
    }


@router.post("", response_model=ApiKeyCreated, status_code=201)
def create_key(data: ApiKeyCreate, user: CurrentUser, session: Database):
    raw_key = issue_api_key()
    key = ApiKey(
        user_id=user.id,
        name=data.name,
        key_prefix=raw_key[:19],
        key_digest=digest_api_key(raw_key),
        key_encrypted=credential_cipher().encrypt(raw_key.encode("utf-8")).decode("ascii"),
        expires_at=data.expires_at,
    )
    session.add(key)
    session.commit()
    session.refresh(key)
    return ApiKeyCreated(**ApiKeySummary.model_validate(key).model_dump(), key=raw_key)


@router.get("/{key_id}/secret", response_model=ApiKeySecret)
def get_key_secret(key_id: int, user: CurrentUser, session: Database):
    key = session.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    if key is None:
        raise HTTPException(404, "API Key 不存在")
    try:
        raw_key = credential_cipher().decrypt(key.key_encrypted.encode("ascii")).decode("utf-8")
    except (HTTPException, ValueError, TypeError) as exc:
        raise HTTPException(503, "API Key 无法解密") from exc
    return ApiKeySecret(key=raw_key)


@router.put("/{key_id}", response_model=ApiKeySummary)
def update_key(key_id: int, data: ApiKeyUpdate, user: CurrentUser, session: Database):
    key = session.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    if key is None:
        raise HTTPException(404, "API Key 不存在")
    key.name = data.name
    key.expires_at = data.expires_at
    session.commit()
    session.refresh(key)
    return key


@router.post("/{key_id}/revoke", status_code=204)
def revoke_key(key_id: int, user: CurrentUser, session: Database) -> None:
    key = session.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    if key is None:
        raise HTTPException(404, "API Key 不存在")
    key.is_active = False
    session.commit()


@router.delete("/{key_id}", status_code=204)
def delete_key(key_id: int, user: CurrentUser, session: Database) -> None:
    key = session.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    if key is None:
        raise HTTPException(404, "API Key 不存在")
    session.delete(key)
    session.commit()
