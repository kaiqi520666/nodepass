import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("nodepass-unused-timing-placeholder")
SESSION_COOKIE = "nodepass_session"


def credential_cipher() -> Fernet:
    key = get_settings().credentials_key
    if key is None:
        raise HTTPException(503, "尚未配置凭证加密主密钥，请执行本地 init-credentials-key")
    try:
        return Fernet(key.get_secret_value().encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(503, "凭证加密主密钥格式不正确") from exc


def issue_api_key() -> str:
    return f"sk-nodepass-{secrets.token_urlsafe(32)}"


def digest_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def issue_session(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "aud": "nodepass-web",
            "iss": "nodepass",
            "iat": now,
            "exp": now + timedelta(hours=settings.session_hours),
        },
        settings.session_secret.get_secret_value(),
        algorithm="HS256",
    )


def read_session(token: str) -> int:
    claims = jwt.decode(
        token,
        get_settings().session_secret.get_secret_value(),
        algorithms=["HS256"],
        audience="nodepass-web",
        issuer="nodepass",
        options={"require": ["sub", "aud", "iss", "iat", "exp"]},
    )
    user_id = int(claims["sub"])
    if user_id <= 0:
        raise ValueError("Invalid subject")
    return user_id
