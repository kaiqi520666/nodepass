import re
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_session
from app.core.security import digest_api_key, read_session
from app.models import ApiKey, User

Database = Annotated[Session, Depends(get_session)]


def current_user(
    session: Database,
    nodepass_session: Annotated[str | None, Cookie()] = None,
) -> User:
    try:
        user_id = read_session(nodepass_session or "")
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise HTTPException(401, "请先登录") from exc
    user = session.scalar(select(User).options(joinedload(User.account)).where(User.id == user_id))
    if not user or not user.is_active:
        raise HTTPException(401, "登录已失效，请重新登录")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def admin_user(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(403, "需要管理员权限")
    return user


AdminUser = Annotated[User, Depends(admin_user)]

bearer = HTTPBearer(auto_error=False)


def api_key_user(
    session: Database,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if not credentials or not re.fullmatch(
        r"sk-nodepass-[A-Za-z0-9_-]{43}", credentials.credentials
    ):
        raise HTTPException(401, "Invalid API key.", headers={"WWW-Authenticate": "Bearer"})
    result = session.execute(
        select(ApiKey, User)
        .join(User, User.id == ApiKey.user_id)
        .where(
            ApiKey.key_digest == digest_api_key(credentials.credentials),
            ApiKey.is_active,
            User.is_active,
            or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > datetime.now(UTC)),
        )
    ).first()
    if not result:
        raise HTTPException(401, "Invalid API key.", headers={"WWW-Authenticate": "Bearer"})
    key, user = result
    key.last_used_at = datetime.now(UTC)
    session.commit()
    return user


ApiKeyUser = Annotated[User, Depends(api_key_user)]
