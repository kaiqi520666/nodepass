import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models import Provider, Task


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, explicit_failure: bool = False):
        super().__init__(message)
        self.explicit_failure = explicit_failure


@dataclass(frozen=True)
class ImageOutput:
    url: str | None = None
    b64_json: str | None = None
    content_type: str = "image/png"


@dataclass(frozen=True)
class ImageResult:
    state: str
    upstream_id: str | None = None
    outputs: tuple[ImageOutput, ...] = ()
    raw_status: str | None = None
    error: str | None = None


def _state(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"completed", "complete", "succeeded", "success", "done"}:
        return "succeeded"
    if raw in {"failed", "failure", "error", "cancelled", "canceled", "rejected"}:
        return "failed"
    if raw in {"queued", "pending", "created"}:
        return "pending"
    return "processing"


def _outputs(payload: dict[str, Any]) -> tuple[ImageOutput, ...]:
    values = payload.get("data") or payload.get("output") or []
    if isinstance(values, dict):
        values = [values]
    result: list[ImageOutput] = []
    for value in values:
        if isinstance(value, str):
            result.append(ImageOutput(url=value))
            continue
        if not isinstance(value, dict):
            continue
        url = value.get("url") or value.get("image_url") or value.get("content_url")
        b64 = value.get("b64_json") or value.get("base64")
        if url or b64:
            result.append(
                ImageOutput(
                    url=url,
                    b64_json=b64,
                    content_type=value.get("content_type") or "image/png",
                )
            )
    return tuple(result)


class CangyuanImageAdapter:
    def __init__(self, provider: Provider, api_key: str):
        self.provider = provider
        self.api_key = api_key
        config = provider.request_config or {}
        self.timeout = int(config.get("timeout_seconds", 60))

    def _request(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None):
        url = f"{self.provider.base_url.rstrip('/')}{path}"
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        )
        request = Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "NodePass/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                message = detail.get("error", {}).get("message") or detail.get("message")
            except (ValueError, AttributeError):
                message = None
            raise ProviderError(
                f"上游请求被拒绝{f': {message}' if message else ''}",
                explicit_failure=exc.code < 500,
            ) from exc
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("上游请求失败，无法确认任务状态") from exc

    def submit(self, task: Task) -> ImageResult:
        params = dict(task.request_params or {})
        payload: dict[str, Any] = {
            "model": task.model_snapshot["upstream_model_id"],
            "prompt": params["prompt"],
            "n": 1,
            "async": True,
        }
        for field in (
            "size",
            "quality",
            "tier",
            "series",
            "background",
            "output_format",
            "response_format",
            "user",
        ):
            if params.get(field) is not None:
                payload[field] = params[field]
        response = self._request("/v1/images/generations", method="POST", payload=payload)
        upstream_id = response.get("id") or response.get("task_id")
        if not upstream_id:
            raise ProviderError("上游响应缺少任务 ID，无法确认受理")
        state = _state(response.get("status"))
        outputs = _outputs(response)
        if outputs:
            state = "succeeded"
        return ImageResult(
            state=state,
            upstream_id=str(upstream_id),
            outputs=outputs,
            raw_status=response.get("status"),
        )

    def query(self, upstream_id: str) -> ImageResult:
        response = self._request(f"/v1/images/generations/{upstream_id}")
        state = _state(response.get("status"))
        outputs = _outputs(response)
        if outputs:
            state = "succeeded"
        error = response.get("error")
        if isinstance(error, dict):
            error = error.get("message")
        return ImageResult(
            state=state,
            upstream_id=upstream_id,
            outputs=outputs,
            raw_status=response.get("status"),
            error=str(error) if error else None,
        )


def decode_output(output: ImageOutput) -> tuple[bytes, str]:
    if output.b64_json:
        try:
            return base64.b64decode(output.b64_json, validate=True), output.content_type
        except (ValueError, TypeError) as exc:
            raise ProviderError("上游 Base64 结果无效") from exc
    if not output.url:
        raise ProviderError("上游结果缺少可下载地址")
    request = Request(output.url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"})
    try:
        with urlopen(request, timeout=60) as response:
            content_type = response.headers.get_content_type() or output.content_type
            return response.read(), content_type
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ProviderError("上游结果下载失败") from exc
