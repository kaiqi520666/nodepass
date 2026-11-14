from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import credential_cipher
from app.models import Model, Provider
from app.schemas_catalog import ModelInput, TextCapabilities, TokenPriceInput
from app.services.catalog_admin import save_model


def seed_gpt_models(session: Session, key: str) -> int:
    provider = session.scalar(select(Provider).where(Provider.adapter_key == "modelgate_openai"))
    if provider is None:
        provider = Provider(
            name="ModelGate GPT",
            adapter_key="modelgate_openai",
            base_url="https://intl.modelgate.top",
            credentials_encrypted=credential_cipher().encrypt(key.encode()).decode("ascii"),
            request_config={
                "timeout_seconds": 300,
                "poll_interval_seconds": 5,
                "task_timeout_seconds": 1800,
            },
            is_active=True,
        )
        session.add(provider)
        session.commit()
    count = 0
    for public_id in ("gpt-6.1-sol",):
        if session.scalar(select(Model.id).where(Model.public_id == public_id)):
            continue
        save_model(
            session,
            ModelInput(
                public_id=public_id,
                display_name=public_id,
                media_type="text",
                provider_id=provider.id,
                upstream_model_id=public_id,
                capabilities=TextCapabilities(),
                token_price=TokenPriceInput(
                    input_price="2",
                    output_price="10",
                    cache_read_price="0.1",
                    cost_multiplier="0.2",
                    sale_multiplier="0.2",
                    long_context_threshold=272000,
                    long_context_input_multiplier="2",
                    long_context_output_multiplier="1.5",
                ),
                is_active=provider.is_active and bool(provider.credentials_encrypted),
            ),
        )
        count += 1
    return count
