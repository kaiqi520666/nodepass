from datetime import UTC, datetime
from decimal import Decimal, localcontext
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.money import money
from app.core.security import credential_cipher
from app.models import CreditAccount, CreditEntry, Model, Provider, TextCall
from app.providers.openai_text import ResponsesClient, TextUsage, responses_request
from app.schemas_catalog import ProviderConfig, TokenPriceInput
from app.schemas_text import ChatRequest, ResponsesRequest


def prepare_text_call(session: Session, user_id: int, payload: ChatRequest | ResponsesRequest):
    result = session.execute(
        select(Model, Provider)
        .options(joinedload(Model.token_price))
        .join(Provider, Model.provider_id == Provider.id)
        .where(Model.public_id == payload.model, Model.media_type == "text")
    ).first()
    if result is None:
        raise HTTPException(404, "Model not found.")
    model, provider = result
    if not model.is_active or not provider.is_active or model.token_price is None:
        raise HTTPException(503, "Model provider is unavailable.")
    if provider.adapter_key != "modelgate_openai":
        raise HTTPException(503, "Model provider is unavailable.")
    try:
        body = responses_request(payload, model.capabilities["input_modalities"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    account = session.get(CreditAccount, user_id, populate_existing=True)
    if account is None:
        raise HTTPException(409, "Credit account is not initialized.")
    if account.available <= 0:
        raise HTTPException(402, "Insufficient credit balance.")
    config = ProviderConfig.model_validate(provider.request_config)
    key = credential_cipher().decrypt(provider.credentials_encrypted.encode()).decode()
    call = TextCall(
        user_id=user_id,
        model_id=model.id,
        provider_id=provider.id,
        endpoint="responses" if isinstance(payload, ResponsesRequest) else "chat/completions",
        status="processing",
        price_snapshot={
            **TokenPriceInput.model_validate(model.token_price, from_attributes=True).model_dump(
                mode="json"
            ),
            "public_id": model.public_id,
            "upstream_model_id": model.upstream_model_id,
            "base_url": provider.base_url,
            "timeout_seconds": config.timeout_seconds,
            "stream": payload.stream,
        },
    )
    session.add(call)
    session.commit()
    return (
        call,
        ResponsesClient(provider.base_url, key, config.timeout_seconds, model.upstream_model_id),
        body,
    )


def token_amounts(usage: TextUsage, price: dict) -> tuple[Decimal, Decimal]:
    with localcontext() as context:
        context.prec = 64
        long_context = usage.input_tokens > price["long_context_threshold"]
        input_multiplier = (
            Decimal(price["long_context_input_multiplier"]) if long_context else Decimal(1)
        )
        output_multiplier = (
            Decimal(price["long_context_output_multiplier"]) if long_context else Decimal(1)
        )
        base = (
            (
                Decimal(usage.input_tokens - usage.cached_tokens) * Decimal(price["input_price"])
                + Decimal(usage.cached_tokens) * Decimal(price["cache_read_price"])
            )
            * input_multiplier
            + Decimal(usage.output_tokens) * Decimal(price["output_price"]) * output_multiplier
        ) / Decimal(1_000_000)
        return (
            money(base * Decimal(price["sale_multiplier"])),
            money(base * Decimal(price["cost_multiplier"])),
        )


def finish_text_call(
    session: Session,
    call_id: UUID,
    usage: TextUsage | None,
    *,
    error: str | None = None,
    rejected: bool = False,
):
    call = session.scalar(
        select(TextCall)
        .where(TextCall.id == call_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if call.status != "processing":
        return
    if usage is None:
        call.status = "failed" if rejected else "usage_unknown"
    else:
        charge, cost = token_amounts(usage, call.price_snapshot)
        account = session.scalar(
            select(CreditAccount)
            .where(CreditAccount.user_id == call.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        account.available -= charge
        call.usage, call.charge_amount, call.cost_amount = usage.as_dict(), charge, cost
        call.status = "failed" if error else "succeeded"
        session.add(
            CreditEntry(
                user_id=call.user_id,
                entry_type="text_charge",
                idempotency_key=f"text:{call.id}:charge",
                amount=charge,
                available_delta=-charge,
                frozen_delta=Decimal(0),
                description=f"文本调用：{call.price_snapshot['public_id']}",
            )
        )
    call.error_message, call.completed_at = error, datetime.now(UTC)
    session.commit()
