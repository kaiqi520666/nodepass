import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from decimal import Decimal

import httpx
import pytest
from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect
from test_accounts import register
from test_openai import auth_headers, create_key

from app.core.money import money
from app.models import CreditAccount, CreditEntry, Model, TextCall
from app.providers.openai_text import TextUsage
from app.schemas_text import ChatRequest
from app.services.text_billing import finish_text_call, prepare_text_call, token_amounts
from app.services.text_catalog import seed_gpt_models
from app.services.text_generation import stream_text

USAGE = {
    "input_tokens": 1000,
    "input_tokens_details": {"cached_tokens": 600},
    "output_tokens": 500,
    "output_tokens_details": {"reasoning_tokens": 300},
}
PRICE = {
    "input_price": "2",
    "output_price": "10",
    "cache_read_price": "0.1",
    "sale_multiplier": "0.2",
    "cost_multiplier": "0.2",
    "long_context_threshold": 272000,
    "long_context_input_multiplier": "2",
    "long_context_output_multiplier": "1.5",
}
CHARGE = Decimal("0.00117200")


def native(text="你好", *, usage=USAGE, output=None, status="completed"):
    return {
        "id": "resp_upstream",
        "object": "response",
        "status": status,
        "output": output
        if output is not None
        else [
            {
                "id": "msg_1",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": usage,
        "safety_identifier": "private-upstream-account",
    }


def events(body=None):
    body = body or native()
    return [
        {"type": "response.created", "response": native(status="in_progress", usage=None)},
        {
            "type": "response.output_text.delta",
            "item_id": "msg_1",
            "output_index": 0,
            "content_index": 0,
            "delta": "你好",
        },
        {"type": "response.completed", "response": body},
    ]


@pytest.fixture
def text_account(client, session):
    user = register(client).json()
    session.get(CreditAccount, user["id"]).available = Decimal("0.00000001")
    seed_gpt_models(session, "test-upstream-secret")
    return user["id"], auth_headers(create_key(client).json()["key"])


@pytest.fixture
def upstream(monkeypatch):
    original, captured, queue = httpx.AsyncClient, [], []

    def handler(request):
        captured.append(request)
        data = queue.pop(0)
        if isinstance(data, Exception):
            raise data
        if isinstance(data, httpx.Response):
            return data
        if isinstance(data, list):
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text="".join(f"data: {json.dumps(item)}\n\n" for item in data),
            )
        return httpx.Response(200, json=data)

    monkeypatch.setattr(
        "app.providers.openai_text.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    return queue, captured


@pytest.mark.parametrize("endpoint", ["responses", "chat"])
@pytest.mark.parametrize("stream", [False, True])
def test_sdk_json_sse_and_eight_decimal_debit(
    client, session, text_account, upstream, endpoint, stream
):
    upstream[0].append(events() if stream else native())
    sdk = OpenAI(
        api_key=text_account[1]["Authorization"].removeprefix("Bearer "),
        base_url="http://testserver/v1",
        http_client=client,
        max_retries=0,
    )
    if endpoint == "responses":
        response = sdk.responses.create(
            model="gpt-6.1-sol", input="hello", stream=stream, store=False
        )
        if stream:
            data = list(response)
            assert data[-1].response.output_text == "你好"
            assert [item.sequence_number for item in data] == list(range(len(data)))
        else:
            assert response.output_text == "你好"
            assert "private-upstream-account" not in response.model_dump_json()
    else:
        response = sdk.chat.completions.create(
            model="gpt-6.1-sol",
            messages=[{"role": "user", "content": "hello"}],
            stream=stream,
            stream_options={"include_usage": True},
        )
        if stream:
            data = list(response)
            assert (
                "".join(item.choices[0].delta.content or "" for item in data if item.choices)
                == "你好"
            )
            assert data[-1].usage.completion_tokens == 500
        else:
            assert response.choices[0].message.content == "你好"
    session.expire_all()
    call = session.scalar(select(TextCall))
    assert call.status == "succeeded"
    assert call.charge_amount == call.cost_amount == CHARGE
    assert session.get(CreditAccount, text_account[0]).available == Decimal("0.00000001") - CHARGE
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 1
    request = upstream[1][0]
    assert request.headers["authorization"] == "Bearer test-upstream-secret"
    assert request.url.path == "/v1/responses"
    log = client.get("/api/account/text-calls").json()
    detail = client.get(f"/api/account/text-calls/{call.id}")
    assert log["data"][0]["charge_amount"] == "0.00117200"
    assert detail.json()["usage"]["reasoning_tokens"] == 300
    for private in ("cost", "provider", "base_url", "upstream", "test-upstream-secret"):
        assert private not in detail.text
    assert seed_gpt_models(session, "unused") == 0


@pytest.mark.parametrize("balance", ["0", "-0.00000001"])
def test_nonpositive_balance_never_calls_upstream(client, session, text_account, upstream, balance):
    session.get(CreditAccount, text_account[0]).available = Decimal(balance)
    session.commit()
    response = client.post(
        "/v1/responses", headers=text_account[1], json={"model": "gpt-6.1-sol", "input": "hi"}
    )
    assert response.status_code == 402
    assert upstream[1] == []
    assert session.scalar(select(func.count()).select_from(TextCall)) == 0


@pytest.mark.parametrize(
    "part",
    [
        {"type": "input_video", "video_url": "https://example.com/video.mp4"},
        {"type": "input_audio", "data": "AAAA", "format": "wav"},
        {"type": "input_image", "image_url": "http://example.com/image.png"},
        {"type": "input_image", "image_url": "data:image/png;base64,INVALID"},
    ],
)
def test_unsupported_media_rejected_before_billing(client, session, text_account, upstream, part):
    result = client.post(
        "/v1/responses",
        headers=text_account[1],
        json={
            "model": "gpt-6.1-sol",
            "input": [{"role": "user", "content": [part]}],
        },
    )
    assert result.status_code == 422
    assert upstream[1] == []
    assert session.scalar(select(func.count()).select_from(TextCall)) == 0


@pytest.mark.parametrize("endpoint", ["responses", "chat/completions"])
def test_image_and_strict_schema_mapping(client, text_account, upstream, endpoint):
    upstream[0].append(native('{"name":"李明"}'))
    schema = {
        "name": "character",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    }
    payload = {"model": "gpt-6.1-sol"}
    image = "https://example.com/portrait.png"
    if endpoint == "responses":
        payload.update(
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": image, "detail": "high"},
                    ],
                }
            ],
            text={"format": {"type": "json_schema", **schema}},
        )
    else:
        payload.update(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image, "detail": "high"}},
                    ],
                }
            ],
            response_format={"type": "json_schema", "json_schema": schema},
        )
    result = client.post(f"/v1/{endpoint}", headers=text_account[1], json=payload)
    assert result.status_code == 200, result.text
    body = json.loads(upstream[1][0].content)
    assert body["input"][0]["content"][0] == {
        "type": "input_image",
        "image_url": image,
        "detail": "high",
    }
    assert body["text"]["format"] == {"type": "json_schema", **schema}


@pytest.mark.parametrize("endpoint", ["responses", "chat"])
@pytest.mark.parametrize("stream", [False, True])
def test_function_round_trip(client, session, text_account, upstream, endpoint, stream):
    session.get(CreditAccount, text_account[0]).available = Decimal("10")
    session.commit()
    item = {
        "id": "fc_1",
        "type": "function_call",
        "call_id": "call_native_1",
        "name": "lookup",
        "arguments": '{"name":"李明"}',
        "status": "completed",
    }
    first = native(output=[item])
    upstream[0].append(
        [
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {**item, "arguments": ""},
            },
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 0,
                "item_id": "fc_1",
                "delta": item["arguments"],
            },
            {"type": "response.completed", "response": first},
        ]
        if stream
        else first
    )
    upstream[0].append(native("found"))
    sdk = OpenAI(
        api_key=text_account[1]["Authorization"].removeprefix("Bearer "),
        base_url="http://testserver/v1",
        http_client=client,
        max_retries=0,
    )
    tool = {
        "name": "lookup",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    }
    prompt = {"role": "user", "content": "查询李明"}
    if endpoint == "responses":
        tools = [{"type": "function", **tool}]
        reply = sdk.responses.create(
            model="gpt-6.1-sol", input=[prompt], tools=tools, tool_choice="required", stream=stream
        )
        if stream:
            reply = list(reply)[-1].response
        assert reply.output[0].call_id == "call_native_1"
        history = [part.model_dump(exclude_unset=True) for part in reply.output]
        reply = sdk.responses.create(
            model="gpt-6.1-sol",
            input=[
                prompt,
                *history,
                {"type": "function_call_output", "call_id": item["call_id"], "output": "found"},
            ],
            tools=tools,
            tool_choice="none",
        )
        assert reply.output_text == "found"
    else:
        tools = [{"type": "function", "function": tool}]
        reply = sdk.chat.completions.create(
            model="gpt-6.1-sol",
            messages=[prompt],
            tools=tools,
            tool_choice="required",
            stream=stream,
        )
        if stream:
            chunks = list(reply)
            calls = [
                chunk.choices[0].delta.tool_calls[0]
                for chunk in chunks
                if chunk.choices and chunk.choices[0].delta.tool_calls
            ]
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": calls[0].id,
                        "type": "function",
                        "function": {
                            "name": calls[0].function.name,
                            "arguments": "".join(call.function.arguments or "" for call in calls),
                        },
                    }
                ],
            }
        else:
            message = reply.choices[0].message.model_dump(exclude_unset=True)
        reply = sdk.chat.completions.create(
            model="gpt-6.1-sol",
            messages=[
                prompt,
                message,
                {"role": "tool", "tool_call_id": item["call_id"], "content": "found"},
            ],
            tools=tools,
            tool_choice="none",
        )
        assert reply.choices[0].message.content == "found"
    assert json.loads(upstream[1][1].content)["input"][-1]["call_id"] == "call_native_1"
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 2


@pytest.mark.parametrize("endpoint", ["responses", "chat/completions"])
@pytest.mark.parametrize("stream", [False, True])
def test_search_and_citations(client, text_account, upstream, endpoint, stream):
    body = native()
    part = body["output"][0]["content"][0]
    part["annotations"] = [
        {
            "type": "url_citation",
            "url": "https://www.python.org/",
            "title": "Python",
            "start_index": 0,
            "end_index": 2,
        },
        {"type": "url_citation", "url": "javascript:alert(1)", "title": "unsafe"},
    ]
    body["output"].insert(
        0,
        {
            "id": "ws_1",
            "type": "web_search_call",
            "status": "completed",
            "action": {"type": "search", "query": "Python"},
        },
    )
    upstream[0].append(events(body) if stream else body)
    payload = {"model": "gpt-6.1-sol", "stream": stream}
    if endpoint == "responses":
        payload.update(input="search", tools=[{"type": "web_search"}])
    else:
        payload.update(messages=[{"role": "user", "content": "search"}], web_search_options={})
    reply = client.post(f"/v1/{endpoint}", headers=text_account[1], json=payload)
    assert reply.status_code == 200, reply.text
    assert "https://www.python.org/" in reply.text
    assert "javascript:" not in reply.text
    assert "private-upstream-account" not in reply.text
    assert json.loads(upstream[1][0].content)["tools"] == [{"type": "web_search"}]


@pytest.mark.parametrize("stream", [False, True])
def test_missing_usage_not_free_success(client, session, text_account, upstream, stream):
    upstream[0].append(events(native(usage=None)) if stream else native(usage=None))
    reply = client.post(
        "/v1/responses",
        headers=text_account[1],
        json={"model": "gpt-6.1-sol", "input": "hi", "stream": stream},
    )
    if stream:
        assert "event: error" in reply.text
        assert "event: response.completed" not in reply.text
    else:
        assert reply.status_code == 502
    session.expire_all()
    assert session.scalar(select(TextCall)).status == "usage_unknown"
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 0


def test_rejection_distinct_from_unknown_submission(client, session, text_account, upstream):
    upstream[0].extend(
        [httpx.ReadTimeout("private"), httpx.Response(429, json={"error": "private"})]
    )
    for status in ("usage_unknown", "failed"):
        reply = client.post(
            "/v1/responses", headers=text_account[1], json={"model": "gpt-6.1-sol", "input": "hi"}
        )
        assert reply.status_code == 502
        assert "private" not in reply.text
        assert (
            session.scalars(select(TextCall).order_by(TextCall.created_at)).all()[-1].status
            == status
        )


def test_pricing_threshold_cache_reasoning_and_rounding():
    assert token_amounts(TextUsage.parse(USAGE), PRICE) == (CHARGE, CHARGE)
    assert token_amounts(TextUsage(272000, 0, 100, 0), PRICE)[0] == Decimal("0.10900000")
    assert token_amounts(TextUsage(272001, 272000, 100, 50), PRICE)[0] == Decimal("0.01118080")
    assert money(Decimal("0.000000005")) == Decimal("0.00000001")
    for invalid in (
        {**USAGE, "input_tokens": -1},
        {**USAGE, "output_tokens": True},
        {**USAGE, "input_tokens_details": {"cached_tokens": 1001}},
        {**USAGE, "output_tokens_details": {"reasoning_tokens": 501}},
    ):
        with pytest.raises(ValueError):
            TextUsage.parse(invalid)


def test_concurrent_settlement_uses_snapshot_once(session, text_account, engine):
    payload = ChatRequest(model="gpt-6.1-sol", messages=[{"role": "user", "content": "hi"}])
    first, _, _ = prepare_text_call(session, text_account[0], payload)
    second, _, _ = prepare_text_call(session, text_account[0], payload)
    model = session.scalar(select(Model).where(Model.public_id == payload.model))
    model.token_price.sale_multiplier = Decimal(99)
    model.token_price.long_context_threshold = 1
    session.commit()

    def charge(call_id):
        with Session(engine) as own:
            finish_text_call(own, call_id, TextUsage.parse(USAGE))

    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(charge, [first.id, second.id, first.id]))
    session.expire_all()
    assert (
        session.get(CreditAccount, text_account[0]).available == Decimal("0.00000001") - CHARGE * 2
    )
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 2


def test_stream_close_drains_and_settles(session, text_account, engine):
    payload = ChatRequest(
        model="gpt-6.1-sol", messages=[{"role": "user", "content": "hi"}], stream=True
    )
    call, _, _ = prepare_text_call(session, text_account[0], payload)

    async def remaining():
        yield {"type": "response.completed", "response": native()}

    async def run():
        stream = stream_text(engine, call, payload, events()[0], remaining())
        await anext(stream)
        await stream.aclose()

    asyncio.run(run())
    session.expire_all()
    assert session.get(TextCall, call.id).charge_amount == CHARGE


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
def test_http_disconnect_still_settles(client, session, text_account, upstream, spec_version):
    upstream[0].append(events())
    body = json.dumps({"model": "gpt-6.1-sol", "input": "hi", "stream": True}).encode()

    async def run():
        disconnected, sent = asyncio.Event(), False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                if disconnected.is_set() and spec_version == "2.4":
                    raise OSError("Client disconnected")
                disconnected.set()
                await asyncio.sleep(0)

        with pytest.raises(ClientDisconnect) if spec_version == "2.4" else nullcontext():
            await client.app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0", "spec_version": spec_version},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/v1/responses",
                    "raw_path": b"/v1/responses",
                    "query_string": b"",
                    "root_path": "",
                    "server": ("testserver", 80),
                    "client": ("127.0.0.1", 1000),
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"authorization", text_account[1]["Authorization"].encode()),
                    ],
                },
                receive,
                send,
            )

    asyncio.run(run())
    session.expire_all()
    assert session.scalar(select(TextCall)).charge_amount == CHARGE


def test_bearer_required_even_with_web_session(client, text_account):
    assert (
        client.post("/v1/responses", json={"model": "gpt-6.1-sol", "input": "hi"}).status_code
        == 401
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"previous_response_id": "resp_1"},
        {"tool_choice": "required"},
        {
            "tools": [{"type": "function", "name": "lookup"}],
            "tool_choice": {"type": "function", "name": "undeclared"},
        },
        {"tools": [{"type": "function", "name": "lookup"}, {"type": "function", "name": "lookup"}]},
        {"input": [{"type": "function_call_output", "call_id": "call_missing", "output": "found"}]},
        {"tools": [{"type": "web_search"}, {"type": "function", "name": "lookup"}]},
        {"tools": [{"type": "web_search"}], "tool_choice": "required"},
        {"text": {"format": {"type": "json_schema", "name": "broken"}}},
    ],
)
def test_invalid_tool_history_or_parameters_never_bill(
    client, session, text_account, upstream, extra
):
    reply = client.post(
        "/v1/responses",
        headers=text_account[1],
        json={"model": "gpt-6.1-sol", "input": "hi", **extra},
    )
    assert reply.status_code == 422
    assert upstream[1] == []
    assert session.scalar(select(func.count()).select_from(TextCall)) == 0


@pytest.mark.parametrize("broken", ["failed", "invalid_output"])
def test_failure_with_reliable_usage_still_bills_once(
    client, session, text_account, upstream, broken
):
    body = native(status="failed") if broken == "failed" else native(output=[{"type": "unknown"}])
    upstream[0].append(body)
    reply = client.post(
        "/v1/responses", headers=text_account[1], json={"model": "gpt-6.1-sol", "input": "hi"}
    )
    assert reply.status_code == 502
    call = session.scalar(select(TextCall))
    assert call.status == "failed"
    assert call.charge_amount == CHARGE
    finish_text_call(session, call.id, TextUsage.parse(USAGE))
    assert session.scalar(select(func.count()).select_from(CreditEntry)) == 1


def test_incomplete_returns_length_without_double_reasoning_charge(
    client, session, text_account, upstream
):
    body = native(status="incomplete")
    body["incomplete_details"] = {"reason": "max_output_tokens"}
    upstream[0].append(body)
    reply = client.post(
        "/v1/chat/completions",
        headers=text_account[1],
        json={
            "model": "gpt-6.1-sol",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert reply.status_code == 200
    assert reply.json()["choices"][0]["finish_reason"] == "length"
    assert session.scalar(select(TextCall)).charge_amount == CHARGE
