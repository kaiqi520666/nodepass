import json
from contextlib import aclosing

import anyio
import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.providers.openai_text import TextUsage
from app.schemas_text import ChatRequest, ResponsesRequest
from app.services.media import validate_https_url
from app.services.text_billing import finish_text_call, prepare_text_call


class TextStreamingResponse(StreamingResponse):
    async def stream_response(self, send):
        try:
            # Finish reading usage even if the caller disconnects during a model response.
            with anyio.CancelScope(shield=True):
                chunk = await anext(self.body_iterator, None)
            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )
            while chunk is not None:
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk.encode(self.charset),
                        "more_body": True,
                    }
                )
                with anyio.CancelScope(shield=True):
                    chunk = await anext(self.body_iterator, None)
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()


def citation(data):
    if data.get("type") != "url_citation":
        return None
    try:
        validate_https_url(data["url"])
    except (KeyError, ValueError):
        return None
    return {
        key: data[key]
        for key in ("type", "url", "title", "start_index", "end_index")
        if key in data
    }


def content_part(part):
    kind = part["type"]
    if kind == "output_text":
        return {
            "type": kind,
            "text": part["text"],
            "annotations": [
                clean for entry in part.get("annotations", []) if (clean := citation(entry))
            ],
        }
    if kind == "refusal":
        return {"type": kind, "refusal": part["refusal"]}
    if kind == "summary_text":
        return {"type": kind, "text": part["text"]}
    raise ValueError("Unsupported upstream output content.")


def output_item(item):
    fields = {
        "message": ("id", "type", "role", "status", "phase"),
        "function_call": ("id", "type", "call_id", "name", "arguments", "status"),
        "reasoning": ("id", "type", "encrypted_content", "status"),
        "web_search_call": ("id", "type", "status"),
    }
    kind = item["type"]
    if kind not in fields:
        raise ValueError("Unsupported upstream output item.")
    clean = {key: item[key] for key in fields[kind] if key in item}
    if kind == "message":
        clean["content"] = [content_part(part) for part in item["content"]]
    elif kind == "reasoning":
        clean["summary"] = [content_part(part) for part in item["summary"]]
    elif kind == "web_search_call":
        clean["action"] = {
            key: value
            for key, value in item["action"].items()
            if key in {"type", "query", "queries", "url", "pattern"}
        }
    return clean


class TextResult:
    def __init__(self, call):
        self.call = call
        self.output = []
        self.usage = None
        self.status = None
        self.incomplete_details = None

    def read(self, data):
        kind = data.get("type")
        if kind in {"response.completed", "response.incomplete", "response.failed"}:
            data = data["response"]
        elif kind:
            if kind == "error":
                raise ValueError("Upstream generation failed.")
            return
        self.status = data["status"]
        if data.get("usage") is not None:
            self.usage = TextUsage.parse(data["usage"])
        self.output = [output_item(item) for item in data["output"]]
        if data.get("incomplete_details"):
            self.incomplete_details = {"reason": data["incomplete_details"]["reason"]}

    @property
    def error(self):
        if self.status is None or self.usage is None:
            return "Upstream response ended without final usage."
        if self.status not in {"completed", "incomplete"}:
            return "Generation could not be completed."
        return None

    @property
    def chat_finish_reason(self):
        if self.status == "incomplete":
            return "length"
        return "tool_calls" if any(i["type"] == "function_call" for i in self.output) else "stop"

    def response_body(self, *, pending=False):
        return {
            "id": f"resp_{self.call.id.hex}",
            "object": "response",
            "created_at": int(self.call.created_at.timestamp()),
            "status": "in_progress" if pending else self.status,
            "model": self.call.price_snapshot["public_id"],
            "output": [] if pending else self.output,
            "usage": usage_body(self.usage, True) if self.usage and not pending else None,
            "error": None,
            "incomplete_details": None if pending else self.incomplete_details,
            "store": False,
        }

    def chat_message(self):
        text, refusal, annotations, calls = "", "", [], []
        for item in self.output:
            if item["type"] == "function_call":
                calls.append(
                    {
                        "id": item["call_id"],
                        "type": "function",
                        "function": {"name": item["name"], "arguments": item["arguments"]},
                    }
                )
            elif item["type"] == "message":
                for part in item["content"]:
                    if part["type"] == "output_text":
                        for entry in part["annotations"]:
                            value = {key: val for key, val in entry.items() if key != "type"}
                            for key in ("start_index", "end_index"):
                                if key in value:
                                    value[key] += len(text)
                            annotations.append({"type": "url_citation", "url_citation": value})
                        text += part["text"]
                    elif part["type"] == "refusal":
                        refusal += part["refusal"]
        message = {"role": "assistant", "content": text if text or not calls else None}
        if calls:
            message["tool_calls"] = calls
        if refusal:
            message["refusal"] = refusal
        if annotations:
            message["annotations"] = annotations
        return message


def usage_body(usage: TextUsage, responses: bool):
    if responses:
        return {
            "input_tokens": usage.input_tokens,
            "input_tokens_details": {"cached_tokens": usage.cached_tokens},
            "output_tokens": usage.output_tokens,
            "output_tokens_details": {"reasoning_tokens": usage.reasoning_tokens},
            "total_tokens": usage.input_tokens + usage.output_tokens,
        }
    return {
        "prompt_tokens": usage.input_tokens,
        "completion_tokens": usage.output_tokens,
        "total_tokens": usage.input_tokens + usage.output_tokens,
        "prompt_tokens_details": {"cached_tokens": usage.cached_tokens},
        "completion_tokens_details": {"reasoning_tokens": usage.reasoning_tokens},
    }


def chat_body(call, *, chunk=False, choices=None, usage=None):
    body = {
        "id": f"chatcmpl-{call.id.hex}",
        "object": "chat.completion.chunk" if chunk else "chat.completion",
        "created": int(call.created_at.timestamp()),
        "model": call.price_snapshot["public_id"],
        "choices": choices or [],
    }
    if usage is not None:
        body["usage"] = usage_body(usage, False)
    return body


async def generate_text(session: Session, user_id: int, payload: ChatRequest | ResponsesRequest):
    call, client, body = prepare_text_call(session, user_id, payload)
    upstream = client.generate(body, payload.stream)
    try:
        first = await anext(upstream)
    except (httpx.HTTPError, ValueError, StopAsyncIteration) as exc:
        rejected = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500
        finish_text_call(
            session, call.id, None, error="Upstream request failed.", rejected=rejected
        )
        await upstream.aclose()
        raise HTTPException(502, "Upstream request failed. Do not resubmit automatically.") from exc
    if payload.stream:
        return TextStreamingResponse(
            stream_text(session.get_bind(), call, payload, first, upstream),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "X-Request-ID": str(call.id)},
        )
    result = TextResult(call)
    try:
        async with aclosing(upstream):
            result.read(first)
            async for data in upstream:
                result.read(data)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        finish_text_call(
            session, call.id, result.usage, error="Invalid or interrupted upstream response."
        )
        raise HTTPException(502, "Invalid or interrupted upstream response.") from None
    finish_text_call(session, call.id, result.usage, error=result.error)
    if result.error:
        raise HTTPException(502, result.error)
    if isinstance(payload, ResponsesRequest):
        return result.response_body()
    return chat_body(
        call,
        choices=[
            {
                "index": 0,
                "message": result.chat_message(),
                "finish_reason": result.chat_finish_reason,
            }
        ],
        usage=result.usage,
    )


async def stream_text(bind, call, payload, first, upstream):
    responses = isinstance(payload, ResponsesRequest)
    result = TextResult(call)
    sequence = 0
    function_indices = {}

    def finish(error=None):
        with Session(bind) as session:
            finish_text_call(session, call.id, result.usage, error=error)

    def event(kind, **fields):
        nonlocal sequence
        value = {"type": kind, "sequence_number": sequence, **fields}
        sequence += 1
        return f"event: {kind}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n"

    def chunk(delta, reason=None):
        return (
            "data: "
            + json.dumps(
                chat_body(
                    call,
                    chunk=True,
                    choices=[
                        {
                            "index": 0,
                            "delta": delta,
                            "finish_reason": reason,
                        }
                    ],
                ),
                ensure_ascii=False,
            )
            + "\n\n"
        )

    def convert(data):
        kind = data["type"]
        result.read(data)
        if kind in {"response.completed", "response.incomplete", "response.failed"}:
            finish(result.error)
            if result.error:
                raise ValueError(result.error)
            if responses:
                yield event(kind, response=result.response_body())
            else:
                annotations = result.chat_message().get("annotations")
                yield chunk(
                    {"annotations": annotations} if annotations else {}, result.chat_finish_reason
                )
                if payload.stream_options and payload.stream_options.include_usage:
                    yield (
                        "data: "
                        + json.dumps(chat_body(call, chunk=True, usage=result.usage))
                        + "\n\n"
                    )
                yield "data: [DONE]\n\n"
            return
        if not responses:
            if kind == "response.output_text.delta":
                yield chunk({"content": data["delta"]})
            elif kind == "response.refusal.delta":
                yield chunk({"refusal": data["delta"]})
            elif kind == "response.output_item.added" and data["item"]["type"] == "function_call":
                item = data["item"]
                index = function_indices.setdefault(data["output_index"], len(function_indices))
                yield chunk(
                    {
                        "tool_calls": [
                            {
                                "index": index,
                                "id": item["call_id"],
                                "type": "function",
                                "function": {"name": item["name"], "arguments": item["arguments"]},
                            }
                        ]
                    }
                )
            elif kind == "response.function_call_arguments.delta":
                yield chunk(
                    {
                        "tool_calls": [
                            {
                                "index": function_indices[data["output_index"]],
                                "function": {"arguments": data["delta"]},
                            }
                        ]
                    }
                )
            return
        if kind in {"response.created", "response.in_progress"}:
            yield event(kind, response=result.response_body(pending=True))
        elif kind in {"response.output_item.added", "response.output_item.done"}:
            yield event(kind, output_index=data["output_index"], item=output_item(data["item"]))
        elif kind in {"response.content_part.added", "response.content_part.done"}:
            yield event(
                kind,
                item_id=data["item_id"],
                output_index=data["output_index"],
                content_index=data["content_index"],
                part=content_part(data["part"]),
            )
        elif kind == "response.output_text.annotation.added":
            if clean := citation(data["annotation"]):
                yield event(
                    kind,
                    **{
                        key: data[key]
                        for key in ("item_id", "output_index", "content_index", "annotation_index")
                    },
                    annotation=clean,
                )
        elif kind in {
            "response.output_text.delta",
            "response.output_text.done",
            "response.refusal.delta",
            "response.refusal.done",
            "response.function_call_arguments.delta",
            "response.function_call_arguments.done",
            "response.reasoning_summary_part.added",
            "response.reasoning_summary_part.done",
            "response.reasoning_summary_text.delta",
            "response.reasoning_summary_text.done",
            "response.web_search_call.in_progress",
            "response.web_search_call.searching",
            "response.web_search_call.completed",
        }:
            fields = {
                key: data[key]
                for key in (
                    "item_id",
                    "output_index",
                    "content_index",
                    "summary_index",
                    "delta",
                    "text",
                    "refusal",
                    "arguments",
                )
                if key in data
            }
            if "part" in data:
                fields["part"] = content_part(data["part"])
            yield event(kind, **fields)

    try:
        if not responses:
            yield chunk({"role": "assistant", "content": ""})
        for data in (first,):
            for value in convert(data):
                yield value
        async for data in upstream:
            for value in convert(data):
                yield value
        if result.error:
            raise ValueError(result.error)
    except (GeneratorExit, anyio.get_cancelled_exc_class()):
        with anyio.CancelScope(shield=True):
            try:
                result.read(first)
                async for data in upstream:
                    result.read(data)
                finish(result.error)
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                finish("Invalid or interrupted upstream response.")
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        finish("Invalid or interrupted upstream response.")
        error = {"type": "server_error", "code": None, "message": "Upstream response interrupted."}
        if responses:
            yield event("error", code=error["code"], message=error["message"], param=None)
        else:
            yield "data: " + json.dumps({"error": error}) + "\n\ndata: [DONE]\n\n"
    finally:
        with anyio.CancelScope(shield=True):
            await upstream.aclose()
