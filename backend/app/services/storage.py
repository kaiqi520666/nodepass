import json
import shutil
import tempfile
from urllib.parse import quote

import oss2
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import credential_cipher
from app.models import SystemSetting
from app.services.media import open_media


def _bucket(session: Session, timeout: int = 60):
    setting = session.get(SystemSetting, "oss")
    if setting is None or not setting.value.get("is_active") or not setting.secret_encrypted:
        raise HTTPException(503, "OSS 尚未启用或配置不完整")
    try:
        credentials = json.loads(
            credential_cipher().decrypt(setting.secret_encrypted.encode("ascii")).decode()
        )
        endpoint = str(setting.value["endpoint"]).strip()
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"
        bucket = oss2.Bucket(
            oss2.Auth(credentials["access_key_id"], credentials["access_key_secret"]),
            endpoint,
            setting.value["bucket"],
            region=setting.value.get("region") or None,
            connect_timeout=timeout,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "OSS 配置不完整") from exc
    return bucket, setting


def upload_result(
    session: Session,
    task_id: str,
    position: int,
    content: bytes,
    content_type: str,
) -> dict[str, str | int]:
    bucket, setting = _bucket(session)
    prefix = str(setting.value.get("object_prefix") or "generated").strip("/")
    extension = content_type.split("/", 1)[-1].split(";")[0] or "bin"
    key = f"{prefix}/{task_id}/{position}.{extension}"
    bucket.put_object(key, content, headers={"Content-Type": content_type})
    public_base_url = str(setting.value["public_base_url"]).rstrip("/")
    return {
        "region": setting.value.get("region", ""),
        "bucket": setting.value["bucket"],
        "object_key": key,
        "public_url": f"{public_base_url}/{quote(key, safe='/')}",
        "content_type": content_type,
        "byte_size": len(content),
    }


def upload_video_result(
    session: Session, task_id: str, position: int, url: str, timeout: int
) -> dict[str, str | int]:
    bucket, setting = _bucket(session, timeout)
    prefix = str(setting.value.get("object_prefix") or "generated").strip("/")
    key = f"{prefix}/{task_id}/{position}.mp4"
    with tempfile.TemporaryFile() as temporary:
        with open_media(url, timeout) as response:
            content_type = response.getheader("Content-Type", "").split(";")[0].lower()
            if content_type in {"application/octet-stream", "binary/octet-stream"}:
                content_type = "video/mp4"
            elif not content_type.startswith("video/"):
                raise ValueError("上游结果不是视频文件")
            expected_size = response.getheader("Content-Length")
            shutil.copyfileobj(response, temporary, length=1024 * 1024)
        byte_size = temporary.tell()
        if not byte_size:
            raise ValueError("上游视频结果为空")
        if expected_size is not None and byte_size != int(expected_size):
            raise OSError("上游视频下载不完整")
        temporary.seek(0)
        bucket.put_object(key, temporary, headers={"Content-Type": content_type})
    return {
        "region": setting.value.get("region", ""),
        "bucket": setting.value["bucket"],
        "object_key": key,
        "public_url": f"{str(setting.value['public_base_url']).rstrip('/')}/{quote(key, safe='/')}",
        "content_type": content_type,
        "byte_size": byte_size,
    }
