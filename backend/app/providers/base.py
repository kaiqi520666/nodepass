import json
from dataclasses import dataclass
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, explicit_failure: bool = False):
        super().__init__(message)
        self.explicit_failure = explicit_failure


@dataclass(frozen=True)
class GenerationOutput:
    url: str | None = None
    b64_json: str | None = None
    content_type: str = "image/png"


@dataclass(frozen=True)
class GenerationResult:
    state: str
    upstream_id: str | None = None
    outputs: tuple[GenerationOutput, ...] = ()
    raw_status: str | None = None
    error: str | None = None


class JsonAdapter:
    def __init__(self, snapshot: dict[str, Any], api_key: str):
        self.base_url = snapshot["base_url"]
        self.timeout = snapshot["request_config"]["timeout_seconds"]
        self.api_key = api_key

    def _request(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None):
        body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        request = Request(
            f"{self.base_url.rstrip('/')}{path}",
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
                result = json.loads(response.read().decode())
                if not isinstance(result, dict):
                    raise ValueError("Expected an object")
                return result
        except HTTPError as exc:
            raise ProviderError(
                f"上游请求返回 HTTP {exc.code}", explicit_failure=400 <= exc.code < 500
            ) from exc
        except (URLError, TimeoutError, OSError, ValueError, HTTPException) as exc:
            raise ProviderError("上游请求失败，无法确认任务状态") from exc
