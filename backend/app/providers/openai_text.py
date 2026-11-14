import base64
import binascii
import json
from dataclasses import asdict, dataclass

import httpx

from app.schemas_text import ChatRequest, ResponsesRequest, web_search_requested
from app.services.media import validate_https_url


def validate_image(url: str) -> None:
    if not url.startswith("data:"):
        validate_https_url(url)
        return
    header, separator, data = url.partition(",")
    if (
        not separator
        or header
        not in {
            "data:image/png;base64",
            "data:image/jpeg;base64",
            "data:image/webp;base64",
            "data:image/gif;base64",
        }
        or not data
    ):
        raise ValueError("图片必须使用 HTTPS URL 或有效的 base64 图片 data URI")
    try:
        base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("图片 base64 编码无效") from exc


def responses_request(payload: ChatRequest | ResponsesRequest, modalities: list[str]) -> dict:
    if isinstance(payload, ResponsesRequest):
        body = payload.model_dump(exclude_none=True, by_alias=True)
        items = body["input"]
        if isinstance(items, str):
            items = [{"role": "user", "content": items}]
        body["include"] = ["reasoning.encrypted_content"]
    else:
        items = []
        for message in payload.messages:
            if message.role == "tool":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": message.content,
                    }
                )
                continue
            if message.content is not None:
                content = message.content
                if isinstance(content, list):
                    content = [
                        {
                            "type": "output_text" if message.role == "assistant" else "input_text",
                            "text": part.text,
                        }
                        if part.type == "text"
                        else {
                            "type": "input_image",
                            "image_url": part.image_url.url,
                            "detail": part.image_url.detail,
                        }
                        for part in content
                    ]
                items.append({"role": message.role, "content": content})
            items.extend(
                {"type": "function_call", "call_id": call.id, **call.function.model_dump()}
                for call in message.tool_calls or []
            )
        body = {
            "model": payload.model,
            "stream": payload.stream,
            "store": False,
            "tools": [
                {"type": "function", **tool.function.model_dump(exclude_none=True)}
                for tool in payload.tools
            ],
        }
        if payload.max_completion_tokens is not None:
            body["max_output_tokens"] = payload.max_completion_tokens
        if payload.response_format is not None:
            format_ = payload.response_format.model_dump(exclude_none=True, by_alias=True)
            body["text"] = {"format": {"type": format_["type"], **format_.get("json_schema", {})}}
        choice = payload.tool_choice
        if choice is not None:
            body["tool_choice"] = (
                choice
                if isinstance(choice, str)
                else {"type": "function", "name": choice.function.name}
            )
    body["input"] = items
    if web_search_requested(payload):
        if payload.tool_choice not in (None, "auto") or len(payload.tools) != (
            0 if isinstance(payload, ChatRequest) else 1
        ):
            raise ValueError("Web search must be used alone with automatic tool selection.")
        body["tools"] = [{"type": "web_search"}]
    definitions = [tool for tool in body["tools"] if tool["type"] == "function"]
    names = {tool["name"] for tool in definitions}
    if len(names) != len(definitions):
        raise ValueError("Function names must be unique.")
    choice = body.get("tool_choice")
    if isinstance(choice, dict) and choice["name"] not in names:
        raise ValueError("tool_choice must name a declared function.")
    if not definitions and choice not in (None, "auto", "none"):
        raise ValueError("This tool_choice requires function tools.")
    pending, seen = set(), set()
    for item in items:
        kind = item.get("type")
        if kind == "function_call":
            call_id = item["call_id"]
            if call_id in seen:
                raise ValueError("Duplicate function call ID.")
            pending.add(call_id)
            seen.add(call_id)
        elif kind == "function_call_output":
            if item["call_id"] not in pending:
                raise ValueError("Tool output must match an unanswered function call.")
            pending.remove(item["call_id"])
        elif kind != "reasoning":
            if pending:
                raise ValueError("Return all function outputs before sending another message.")
            content = item["content"]
            if isinstance(content, list):
                for part in content:
                    if part["type"] == "input_image":
                        if item["role"] != "user" or "image" not in modalities:
                            raise ValueError("该消息或模型不支持图片输入")
                        validate_image(part["image_url"])
    if pending:
        raise ValueError("Return all function outputs before sending another message.")
    return body


@dataclass(frozen=True)
class TextUsage:
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    reasoning_tokens: int

    @classmethod
    def parse(cls, usage: dict):
        values = [
            usage["input_tokens"],
            usage.get("input_tokens_details", {}).get("cached_tokens", 0),
            usage["output_tokens"],
            usage.get("output_tokens_details", {}).get("reasoning_tokens", 0),
        ]
        if (
            any(type(value) is not int or value < 0 for value in values)
            or values[1] > values[0]
            or values[3] > values[2]
            or usage.get("input_tokens_details", {}).get("cache_write_tokens", 0)
        ):
            raise ValueError("无效或尚不支持的上游 token 用量")
        return cls(*values)

    def as_dict(self):
        return asdict(self)


class ResponsesClient:
    def __init__(self, base_url: str, key: str, timeout: int, model: str):
        self.base_url, self.key, self.timeout, self.model = base_url, key, timeout, model

    async def generate(self, body: dict, stream: bool):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/responses",
                headers={"Authorization": f"Bearer {self.key}"},
                json={**body, "model": self.model},
            ) as response:
                response.raise_for_status()
                if not stream:
                    yield json.loads(await response.aread())
                    return
                lines = []
                async for line in response.aiter_lines():
                    if not line:
                        if lines:
                            data = "\n".join(lines)
                            lines.clear()
                            if data != "[DONE]":
                                yield json.loads(data)
                    elif line.startswith("data:"):
                        lines.append(line[5:].lstrip())
                if lines and (data := "\n".join(lines)) != "[DONE]":
                    yield json.loads(data)
