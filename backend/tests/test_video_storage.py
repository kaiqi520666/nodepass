import io
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.services import media, storage


@pytest.mark.parametrize("content_type", ["video/mp4", "binary/octet-stream"])
@pytest.mark.parametrize("fail", [False, True])
def test_video_streams_in_chunks_and_temporary_file_is_closed(monkeypatch, fail, content_type):
    content = b"video" * 600_000
    sizes = []
    files = []

    class Response(io.BytesIO):
        def getheader(self, name, default=None):
            return {"Content-Type": content_type, "Content-Length": str(len(content))}.get(
                name, default
            )

        def read(self, size=-1):
            assert 0 < size <= 1024 * 1024
            sizes.append(size)
            return super().read(size)

    @contextmanager
    def download(_url, timeout):
        assert timeout == 900
        with Response(content) as response:
            yield response

    class Bucket:
        def put_object(self, key, file, headers):
            files.append(file)
            assert key == "generated/task/0.mp4" and headers["Content-Type"] == "video/mp4"
            assert file.read() == content
            if fail:
                raise OSError("mock upload failed")

    setting = SimpleNamespace(
        value={
            "object_prefix": "generated",
            "region": "test",
            "bucket": "test",
            "public_base_url": "https://media.example.com",
        }
    )
    monkeypatch.setattr(storage, "_bucket", lambda _session, _timeout: (Bucket(), setting))
    monkeypatch.setattr(storage, "open_media", download)
    if fail:
        with pytest.raises(OSError):
            storage.upload_video_result(None, "task", 0, "https://example.com/a.mp4", 900)
    else:
        result = storage.upload_video_result(None, "task", 0, "https://example.com/a.mp4", 900)
        assert result["byte_size"] == len(content)
        assert result["public_url"] == "https://media.example.com/generated/task/0.mp4"
    assert len(sizes) >= 3 and files[0].closed


def test_partial_download_is_not_uploaded_and_closes_temporary_file(monkeypatch):
    files = []
    temporary_file = storage.tempfile.TemporaryFile

    def temporary():
        file = temporary_file()
        files.append(file)
        return file

    class Response(io.BytesIO):
        def getheader(self, name, default=None):
            return {"Content-Type": "video/mp4", "Content-Length": "999"}.get(name, default)

    @contextmanager
    def download(*_args):
        with Response(b"partial") as response:
            yield response

    setting = SimpleNamespace(value={"object_prefix": "generated"})
    monkeypatch.setattr(storage, "_bucket", lambda *_args: (object(), setting))
    monkeypatch.setattr(storage, "open_media", download)
    monkeypatch.setattr(storage.tempfile, "TemporaryFile", temporary)
    with pytest.raises(OSError, match="不完整"):
        storage.upload_video_result(None, "task", 0, "https://example.com/a.mp4", 60)
    assert len(files) == 1 and files[0].closed


def test_download_rejects_private_dns_before_opening_socket(monkeypatch):
    monkeypatch.setattr(
        media.socket, "getaddrinfo", lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))]
    )
    with pytest.raises(ValueError, match="内网"), media.open_media("https://example.com/a.mp4", 60):
        pytest.fail("Private address was accepted")


def test_download_rejects_private_redirect(monkeypatch):
    monkeypatch.setattr(
        media.socket, "getaddrinfo", lambda *_args, **_kwargs: [(2, 1, 6, "", ("1.1.1.1", 443))]
    )
    monkeypatch.setattr(media.socket, "create_connection", lambda *_args: object())
    monkeypatch.setattr(
        media.ssl,
        "create_default_context",
        lambda: SimpleNamespace(wrap_socket=lambda *_args, **_kwargs: object()),
    )

    class Connection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return SimpleNamespace(status=302, getheader=lambda _name: "https://127.0.0.1/private")

        def close(self):
            pass

    monkeypatch.setattr(media.http.client, "HTTPSConnection", Connection)
    with pytest.raises(ValueError), media.open_media("https://example.com/a.mp4", 60):
        pytest.fail("Private redirect was accepted")
