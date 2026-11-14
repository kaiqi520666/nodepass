import os
import secrets
import uuid
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session, get_session_factory
from app.models import Base


@pytest.fixture(scope="session")
def engine():
    admin_url = make_url(
        os.environ.get(
            "NODEPASS_TEST_DATABASE_URL",
            "postgresql://nodepass:nodepass-local-only@127.0.0.1:55432/postgres",
        )
    )
    if admin_url.host not in {"127.0.0.1", "localhost"}:
        pytest.fail("Tests only create databases on an explicitly local PostgreSQL server")
    database_name = f"nodepass_test_{uuid.uuid4().hex}"
    admin = psycopg.connect(admin_url.render_as_string(hide_password=False), autocommit=True)
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    test_url = admin_url.set(database=database_name, drivername="postgresql+psycopg")
    test_engine = create_engine(test_url, hide_parameters=True)
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("NODEPASS_DATABASE_URL", test_url.render_as_string(hide_password=False))
            patch.setenv("NODEPASS_SESSION_SECRET", secrets.token_urlsafe(48))
            patch.setenv("NODEPASS_CREDENTIALS_KEY", Fernet.generate_key().decode("ascii"))
            patch.setenv("NODEPASS_COOKIE_SECURE", "false")
            patch.setenv("NODEPASS_ENVIRONMENT", "development")
            get_settings.cache_clear()
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            command.upgrade(config, "head")
            yield test_engine
            factory = get_session_factory()
            factory.kw["bind"].dispose()
            get_session_factory.cache_clear()
            get_settings.cache_clear()
    finally:
        test_engine.dispose()
        admin.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
        )
        admin.close()


@pytest.fixture
def session(engine):
    with Session(engine, expire_on_commit=False) as session:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name == "admin_actions":
                session.execute(text("TRUNCATE TABLE admin_actions RESTART IDENTITY"))
            else:
                session.execute(table.delete())
        session.commit()
        yield session
        session.rollback()


@pytest.fixture
def client(session):
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app, headers={"Origin": "http://localhost:5173"}) as client:
        yield client
