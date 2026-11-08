from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.security import DUMMY_HASH, password_hash
from app.models import CreditAccount, User
from app.schemas import Credentials


def register(session: Session, credentials: Credentials, *, is_admin: bool = False) -> User:
    email = str(credentials.email)
    user = User(
        email=email,
        email_normalized=email.lower(),
        password_hash=password_hash.hash(credentials.password.get_secret_value()),
        is_admin=is_admin,
        account=CreditAccount(),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "该邮箱已注册，请直接登录") from exc
    return user


def authenticate(session: Session, credentials: Credentials) -> User:
    user = session.scalar(
        select(User)
        .options(joinedload(User.account))
        .where(User.email_normalized == str(credentials.email).lower())
    )
    valid = password_hash.verify(
        credentials.password.get_secret_value(), user.password_hash if user else DUMMY_HASH
    )
    if not user or not valid or not user.is_active:
        raise HTTPException(401, "邮箱或密码不正确")
    return user
