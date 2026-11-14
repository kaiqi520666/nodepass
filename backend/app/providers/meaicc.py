from decimal import Decimal
from urllib.parse import quote

from app.models import Task
from app.providers.base import GenerationOutput, GenerationResult, JsonAdapter, ProviderError


def _result(response: dict, upstream_id: str | None = None) -> GenerationResult:
    raw = str(response.get("status") or "")
    status = raw.strip().upper()
    if status.startswith("FAILED"):
        return GenerationResult(state="failed", raw_status=raw, error="上游视频生成失败")
    task_id = response.get("task_id") or response.get("id") or upstream_id
    if not isinstance(task_id, str) or not task_id.strip():
        raise ProviderError("上游响应缺少任务 ID，无法确认受理")
    outputs = ()
    if status == "SUCCEEDED":
        url = response.get("object")
        if not isinstance(url, str) or not url:
            raise ProviderError("上游成功响应缺少视频地址")
        outputs = (GenerationOutput(url=url, content_type="video/mp4"),)
    return GenerationResult(
        state="succeeded" if outputs else "pending" if status == "PENDING" else "processing",
        upstream_id=task_id,
        outputs=outputs,
        raw_status=raw,
    )


class MeaiccVideoAdapter(JsonAdapter):
    def submit(self, task: Task) -> GenerationResult:
        params = task.request_params
        seconds = Decimal(params["seconds"])
        media = [
            {
                "type": "reference_voice" if item["type"] == "reference_audio" else item["type"],
                "url": item["url"],
            }
            for item in params["references"]
        ]
        payload = {
            "model": task.model_snapshot["upstream_model_id"],
            "input": {"prompt": params["prompt"], "media": media},
            "parameters": {
                "duration": int(seconds)
                if seconds == seconds.to_integral_value()
                else float(seconds),
                "resolution": params["resolution"],
                "ratio": params["aspect_ratio"],
            },
        }
        return _result(self._request("/v1/videos", method="POST", payload=payload))

    def query(self, task: Task) -> GenerationResult:
        upstream_id = task.upstream_task_id
        return _result(self._request(f"/v1/videos/{quote(upstream_id, safe='')}"), upstream_id)
