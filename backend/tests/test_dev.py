import signal
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from sqlalchemy.exc import OperationalError

from app import dev


@pytest.mark.parametrize("database_state", ["running", "stopped", "custom"])
def test_database_preparation(monkeypatch, database_state):
    database = MagicMock()
    run = MagicMock()
    url = "postgresql+psycopg://nodepass@127.0.0.1:55432/nodepass"
    if database_state == "custom":
        url = "postgresql+psycopg://nodepass@127.0.0.1:5432/custom"
    if database_state != "running":
        database.return_value.__enter__.return_value.execute.side_effect = [
            OperationalError(None, None, Exception("Database unavailable")),
            None,
        ]
    monkeypatch.setattr(dev, "get_session_factory", lambda: database)
    monkeypatch.setattr(dev, "get_settings", lambda: SimpleNamespace(database_url=url))
    monkeypatch.setattr(dev.subprocess, "run", run)
    if database_state == "custom":
        with pytest.raises(RuntimeError, match="数据库无法连接"):
            dev.prepare_database()
        run.assert_not_called()
        return
    dev.prepare_database()
    commands = [call.args[0] for call in run.call_args_list]
    assert commands[-1] == [sys.executable, "-m", "alembic", "upgrade", "head"]
    if database_state == "stopped":
        assert commands[0] == ["docker", "compose", "up", "-d", "--wait", "postgres"]
    else:
        assert len(commands) == 1


@pytest.mark.parametrize("failed_process", [0, 1])
def test_server_exit_stops_both_processes(monkeypatch, failed_process):
    popen = subprocess.Popen
    processes = []

    def start(command, **kwargs):
        script = "import time; time.sleep(60)"
        if len(processes) == failed_process:
            script = "import time; time.sleep(0.1); raise SystemExit(7)"
        process = popen([sys.executable, "-c", script], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(dev.subprocess, "Popen", start)
    assert dev.run_servers() == 7
    assert len(processes) == 2
    assert all(process.poll() is not None for process in processes)


@pytest.mark.parametrize("interrupt_startup", [False, True])
def test_interruption_stops_started_processes(monkeypatch, interrupt_startup):
    popen = subprocess.Popen
    sleep = dev.time.sleep
    processes = []

    def interrupt(*args):
        monkeypatch.setattr(dev.time, "sleep", sleep)
        raise KeyboardInterrupt

    def start(command, **kwargs):
        if interrupt_startup and processes:
            raise OSError("Cannot start second process")
        process = popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(dev.subprocess, "Popen", start)
    if not interrupt_startup:
        monkeypatch.setattr(dev.time, "sleep", interrupt)
    with pytest.raises(OSError if interrupt_startup else KeyboardInterrupt):
        dev.run_servers()
    assert processes
    assert all(process.poll() is not None for process in processes)


def test_launcher_with_temporary_database(session, tmp_path):
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", 8000))
        except OSError:
            pytest.skip("Local API port is occupied")

    with (tmp_path / "dev.log").open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "app.dev"],
            cwd=dev.BACKEND,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            ready = False
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    with urlopen("http://127.0.0.1:8000/health/ready", timeout=0.5) as response:
                        ready = response.status == 200
                except URLError:
                    pass
                if ready:
                    break
                time.sleep(0.1)
            log.seek(0)
            assert ready, log.read()
            process.send_signal(signal.SIGINT)
            assert process.wait(timeout=15) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
        with socket.socket() as connection:
            assert connection.connect_ex(("127.0.0.1", 8000)) != 0
