import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import get_session_factory

BACKEND = Path(__file__).resolve().parents[1]


def prepare_database() -> None:
    try:
        with get_session_factory()() as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        url = make_url(get_settings().database_url)
        if (url.host, url.port, url.database, url.username) != (
            "127.0.0.1",
            55432,
            "nodepass",
            "nodepass",
        ):
            raise RuntimeError("配置的数据库无法连接，请先启动该数据库") from None
        print("正在启动本地 PostgreSQL，请确保 Docker 已启动。", flush=True)
        subprocess.run(
            ["docker", "compose", "up", "-d", "--wait", "postgres"],
            cwd=BACKEND.parent,
            check=True,
        )
        with get_session_factory()() as session:
            session.execute(text("SELECT 1"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)


def run_servers() -> int:
    processes = []
    try:
        for command in (
            [
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            ["-m", "app.worker"],
        ):
            processes.append(subprocess.Popen([sys.executable, *command], start_new_session=True))
        print("API：http://127.0.0.1:8000；Worker 已启动。按 Ctrl+C 一起停止。", flush=True)
        while True:
            for process in processes:
                if process.poll() is not None:
                    print("后端进程已退出，正在停止其余进程。", file=sys.stderr)
                    return process.returncode or 1
            time.sleep(0.2)
    finally:
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def main() -> int:
    os.chdir(BACKEND)
    if get_settings().environment != "development":
        print("此命令仅用于本地开发。", file=sys.stderr)
        return 1

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 8000))
        prepare_database()
        return run_servers()
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError, SQLAlchemyError, subprocess.CalledProcessError):
        print(
            "启动失败：请检查 8000 端口、Docker 和数据库；迁移错误见上方输出。",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
