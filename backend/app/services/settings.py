import json
import time
from uuid import uuid4

import oss2
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import credential_cipher
from app.models import SystemSetting
from app.schemas import OssSettingsInput, OssSettingsSummary, OssTestResult

OSS_KEY = "oss"


def _secret_payload(access_key_id: str, access_key_secret: str) -> str:
    return (
        credential_cipher()
        .encrypt(
            json.dumps(
                {"access_key_id": access_key_id, "access_key_secret": access_key_secret},
                ensure_ascii=False,
            ).encode("utf-8")
        )
        .decode("ascii")
    )


def oss_summary(setting: SystemSetting | None) -> OssSettingsSummary:
    value = setting.value if setting else {}
    secret = bool(setting and setting.secret_encrypted)
    access_key_id = ""
    if secret:
        try:
            access_key_id = json.loads(
                credential_cipher().decrypt(setting.secret_encrypted.encode("ascii")).decode()
            ).get("access_key_id", "")
        except (ValueError, TypeError, KeyError):
            access_key_id = ""
    return OssSettingsSummary(
        endpoint=value.get("endpoint", ""),
        region=value.get("region", ""),
        bucket=value.get("bucket", ""),
        access_key_id=access_key_id,
        public_base_url=value.get("public_base_url", ""),
        object_prefix=value.get("object_prefix", "generated"),
        is_active=bool(value.get("is_active", False)),
        has_credentials=secret,
    )


def save_oss_settings(session: Session, payload: OssSettingsInput) -> OssSettingsSummary:
    setting = session.get(SystemSetting, OSS_KEY)
    secret = payload.access_key_secret.get_secret_value() if payload.access_key_secret else ""
    if setting is None and not secret:
        raise HTTPException(422, "首次配置 OSS 必须填写 AccessKey Secret")
    setting = setting or SystemSetting(key=OSS_KEY)
    setting.value = {
        "endpoint": payload.endpoint,
        "region": payload.region,
        "bucket": payload.bucket,
        "public_base_url": payload.public_base_url.rstrip("/"),
        "object_prefix": payload.object_prefix.strip("/"),
        "is_active": payload.is_active,
    }
    if secret:
        setting.secret_encrypted = _secret_payload(payload.access_key_id, secret)
    elif setting.secret_encrypted is None:
        raise HTTPException(422, "OSS 凭证不完整，请填写 AccessKey Secret")
    session.add(setting)
    session.commit()
    return oss_summary(setting)


def test_oss_connection(session: Session) -> OssTestResult:
    setting = session.get(SystemSetting, OSS_KEY)
    if setting is None or not setting.secret_encrypted:
        raise HTTPException(422, "请先保存完整的 OSS 配置")
    try:
        credentials = json.loads(
            credential_cipher().decrypt(setting.secret_encrypted.encode("ascii")).decode()
        )
        endpoint = setting.value["endpoint"].strip()
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"
        auth = oss2.Auth(credentials["access_key_id"], credentials["access_key_secret"])
        bucket = oss2.Bucket(
            auth,
            endpoint,
            setting.value["bucket"],
            region=setting.value.get("region") or None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, "OSS 配置不完整，请重新保存") from exc

    object_key = (
        f"{setting.value.get('object_prefix', 'generated').strip('/')}/"
        f".nodepass-oss-test/{uuid4().hex}.txt"
    )
    content = b"NodePass OSS connection test"
    started = time.perf_counter()
    uploaded = False
    try:
        bucket.put_object(object_key, content)
        uploaded = True
        if bucket.get_object(object_key).read() != content:
            return OssTestResult(
                ok=False, message="OSS 测试对象内容校验失败", object_key=object_key
            )
        return OssTestResult(
            ok=True,
            message="OSS 连接、写入和读取测试成功",
            object_key=object_key,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
    except Exception:
        return OssTestResult(
            ok=False,
            message="OSS 测试失败，请检查 Endpoint、Region、Bucket 和访问凭证",
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
    finally:
        if uploaded:
            try:
                bucket.delete_object(object_key)
            except Exception:
                pass
