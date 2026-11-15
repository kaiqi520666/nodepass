import base64
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.models import Task
from app.providers.base import GenerationOutput, GenerationResult, JsonAdapter, ProviderError


def _state(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"completed", "complete", "succeeded", "success", "done"}:
        return "succeeded"
    if raw in {"failed", "failure", "error", "cancelled", "canceled", "rejected"}:
        return "failed"
    if raw in {"queued", "pending", "created"}:
        return "pending"
    return "processing"


def _outputs(payload: dict[str, Any]) -> tuple[GenerationOutput, ...]:
    values = payload.get("data") or payload.get("output") or []
    if isinstance(values, dict):
        values = [values]
    result: list[GenerationOutput] = []
    for value in values:
        if isinstance(value, str):
            result.append(GenerationOutput(url=value))
            continue
        if not isinstance(value, dict):
            continue
        url = value.get("url") or value.get("image_url") or value.get("content_url")
        b64 = value.get("b64_json") or value.get("base64")
        if url or b64:
            result.append(
                GenerationOutput(
                    url=url,
                    b64_json=b64,
                    content_type=value.get("content_type") or "image/png",
                )
            )
    return tuple(result)


class CangyuanImageAdapter(JsonAdapter):
    def submit(self, task: Task) -> GenerationResult:
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
        operation = "edits" if "images" in params else "generations"
        if operation == "edits":
            payload["images"] = [item["image_url"] for item in params["images"]]
            if params.get("mask"):
                payload["mask"] = params["mask"]["image_url"]
        response = self._request(f"/v1/images/{operation}", method="POST", payload=payload)
        upstream_id = response.get("id") or response.get("task_id")
        if not upstream_id:
            raise ProviderError("上游响应缺少任务 ID，无法确认受理")
        state = _state(response.get("status"))
        outputs = _outputs(response)
        if outputs:
            state = "succeeded"
        return GenerationResult(
            state=state,
            upstream_id=str(upstream_id),
            outputs=outputs,
            raw_status=response.get("status"),
        )

    def query(self, task: Task) -> GenerationResult:
        upstream_id = task.upstream_task_id
        operation = "edits" if "images" in task.request_params else "generations"
        response = self._request(f"/v1/images/{operation}/{quote(upstream_id, safe='')}")
        state = _state(response.get("status"))
        outputs = _outputs(response)
        if outputs:
            state = "succeeded"
        error = response.get("error")
        if isinstance(error, dict):
            error = error.get("message")
        return GenerationResult(
            state=state,
            upstream_id=upstream_id,
            outputs=outputs,
            raw_status=response.get("status"),
            error=str(error) if error else None,
        )


def decode_output(output: GenerationOutput) -> tuple[bytes, str]:
    if output.b64_json:
        try:
            return base64.b64decode(output.b64_json, validate=True), output.content_type
        except (ValueError, TypeError) as exc:
            raise ProviderError("上游 Base64 结果无效", explicit_failure=True) from exc
    if not output.url:
        raise ProviderError("上游结果缺少可下载地址")
    request = Request(output.url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"})
    try:
        with urlopen(request, timeout=60) as response:
            content_type = response.headers.get_content_type() or output.content_type
            return response.read(), content_type
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ProviderError("上游结果下载失败") from exc
