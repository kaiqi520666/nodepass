from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from test_accounts import CREDENTIALS, register
from test_catalog import add_model

from app.models import CreditAccount, CreditEntry, Model, TextCall
from app.schemas_text import ChatRequest
from app.services.text_billing import prepare_text_call
from app.services.text_catalog import seed_gpt_models


@pytest.fixture
def call_log(client, session):
    user = register(client).json()
    session.get(CreditAccount, user["id"]).available = Decimal("10")
    seed_gpt_models(session, "test-secret")
    call, _, _ = prepare_text_call(
        session,
        user["id"],
        ChatRequest(model="gpt-6.1-sol", messages=[{"role": "user", "content": "hello"}]),
    )
    start = datetime(2026, 11, 1, tzinfo=UTC)
    call.created_at = start
    calls = [call]
    for index, status in enumerate(["succeeded", "failed", "usage_unknown"], 1):
        calls.append(
            TextCall(
                user_id=user["id"],
                model_id=call.model_id,
                provider_id=call.provider_id,
                endpoint="responses",
                status=status,
                price_snapshot={**call.price_snapshot, "public_id": "fixture-text"},
                created_at=start + timedelta(days=index),
                completed_at=start + timedelta(days=index, seconds=2),
                usage=(
                    {
                        "input_tokens": 0,
                        "cached_tokens": 0,
                        "output_tokens": 0,
                        "reasoning_tokens": 0,
                    }
                    if status == "succeeded"
                    else None
                ),
                charge_amount=Decimal(0) if status == "succeeded" else None,
                cost_amount=Decimal(0) if status == "succeeded" else None,
                error_message=None,
            )
        )
    session.add_all(calls)
    session.commit()
    return user["id"], calls


def test_text_log_filters_dates_pagination_and_nullable_charge(client, session, call_log):
    user_id, calls = call_log
    response = client.get("/api/account/text-calls?offset=1&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    assert data["models"] == ["fixture-text", "gpt-6.1-sol"]
    assert [row["id"] for row in data["data"]] == [str(calls[2].id), str(calls[1].id)]
    assert data["data"][0]["charge_amount"] is None
    assert data["data"][1]["charge_amount"] == "0.00000000"
    assert data["data"][1]["input_tokens"] == 0
    for call in calls:
        filtered = client.get("/api/account/text-calls", params={"status": call.status}).json()
        assert filtered["total"] == 1
        assert filtered["data"][0]["id"] == str(call.id)
    filtered = client.get(
        "/api/account/text-calls",
        params={
            "model": "fixture-text",
            "query": str(calls[2].id)[8:18],
            "status": "failed",
            "created_from": int(calls[2].created_at.timestamp()),
            "created_to": int(calls[3].created_at.timestamp()),
        },
    ).json()
    assert filtered["total"] == 1
    assert filtered["data"][0]["id"] == str(calls[2].id)
    assert client.get("/api/account/text-calls?query=%").json()["total"] == 0
    assert client.get("/api/account/text-calls?model=absent").json()["total"] == 0
    assert client.get("/api/account/text-calls?created_from=2&created_to=1").status_code == 422
    assert client.get("/api/account/text-calls?status=invalid").status_code == 422
    assert client.get("/api/account/text-calls?offset=-1").status_code == 422
    call = calls[0]
    session.add_all(
        [
            TextCall(
                user_id=user_id,
                model_id=call.model_id,
                provider_id=call.provider_id,
                endpoint=call.endpoint,
                status="processing",
                price_snapshot=call.price_snapshot,
            )
            for _ in range(101)
        ]
    )
    session.commit()
    last_page = client.get("/api/account/text-calls?offset=100&limit=20").json()
    assert last_page["total"] == 105
    assert len(last_page["data"]) == 5


def test_text_log_ownership_session_auth_and_no_delete(client, call_log):
    _, calls = call_log
    path = f"/api/account/text-calls/{calls[0].id}"
    assert client.get(path).status_code == 200
    assert client.delete(path).status_code == 405
    assert client.get(f"/api/account/text-calls/{uuid4()}").status_code == 404
    client.post("/api/account/logout")
    for url in ("/api/account/text-calls", path, "/api/account/dashboard"):
        assert client.get(url).status_code == 401
    client.post(
        "/api/account/register", json={**CREDENTIALS, "email": "other@example.com"}
    ).raise_for_status()
    assert client.get(path).status_code == 404
    assert client.get("/api/account/text-calls").json() == {"data": [], "total": 0, "models": []}
    dashboard = client.get("/api/account/dashboard").json()
    assert {
        key: dashboard[key] for key in ("available", "consumed", "requests", "today_consumed")
    } == {
        "available": "0.00000000",
        "consumed": "0.00000000",
        "requests": 0,
        "today_consumed": "0.00000000",
    }
    assert len(dashboard["trend"]) == 7
    assert all(row["consumed"] == "0.00000000" for row in dashboard["trend"])


def test_dashboard_counts_generation_and_text_and_only_settled_spending(client, session, call_log):
    user_id, _ = call_log
    _, model, _ = add_model(session)
    session.get(CreditAccount, user_id).available = Decimal("10")
    session.commit()
    key = client.post("/api/account/keys", json={"name": "stats test"}).json()["key"]
    response = client.post(
        "/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model.public_id, "prompt": "test"},
    )
    assert response.status_code == 202
    today = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    entries = [
        ("settle", "1.23000000", today - timedelta(microseconds=1)),
        ("text_charge", "0.00035201", today),
        ("settle", "1.80000000", today),
        ("refund", "0.10000000", today),
        ("admin_credit", "100", today),
        ("admin_debit", "10", today),
        ("recharge", "50", today),
        ("release", "5", today),
    ]
    for index, (kind, amount, created) in enumerate(entries):
        session.add(
            CreditEntry(
                user_id=user_id,
                entry_type=kind,
                idempotency_key=f"stats-test-{index}",
                amount=Decimal(amount),
                available_delta=0,
                frozen_delta=0,
                description="stats test",
                created_at=created,
            )
        )
    session.commit()
    stats = client.get("/api/account/dashboard").json()
    assert {key: stats[key] for key in ("available", "consumed", "requests", "today_consumed")} == {
        "available": "8.77000000",
        "consumed": "2.93035201",
        "requests": 5,
        "today_consumed": "1.70035201",
    }
    trend = {row["date"]: row["consumed"] for row in stats["trend"]}
    assert len(trend) == 7
    assert trend[(today - timedelta(days=1)).date().isoformat()] == "1.23000000"
    assert trend[today.date().isoformat()] == "1.70035201"
    model = session.scalar(select(Model).where(Model.public_id == "gpt-6.1-sol"))
    model.token_price.sale_multiplier = Decimal("2")
    session.commit()
    detail = client.get(f"/api/account/text-calls/{call_log[1][0].id}").json()
    assert detail["sale_price"]["sale_multiplier"] == "0.20000000"
