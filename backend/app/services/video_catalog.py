from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Model, ModelPrice, Provider

# Initial import only; subsequent edits belong to the database and administration forms.
VIDEO_MODELS = [
    ("sd-2-c4", "seedance-2.0", "fast", "720p", 4, 15, "video", "1.8000", False),
    ("sd-2-c5", "seedance-2.0", "fast", "720p", 4, 15, "video", "2.5000", True),
    ("sd-2-c7", "seedance-2.0", "fast", "720p", 4, 15, "video", "2.8000", True),
    ("sd-2-c8", "seedance-2.0", "full", "720p", 4, 15, "video", "3.8000", True),
    ("sd-2.5-c2", "seedance-2.5", "", "720p", 5, 30, "video", "6.2000", False),
    ("sd-2.5-c3", "seedance-2.5", "", "720p", 4, 30, "video", "7.7000", True),
    ("sd-2.5-d1-480", "seedance-2.5", "", "480p", 4, 30, "second", "0.4700", True),
    ("sd-2.5-d1-720", "seedance-2.5", "", "720p", 4, 30, "second", "0.5400", True),
    ("sd-2.5-d2", "seedance-2.5", "", "480p", 5, 30, "second", "0.2900", False),
    ("sd-2.5-d3", "seedance-2.5", "", "720p", 5, 30, "second", "0.3900", False),
]


def video_profiles() -> list[dict]:
    return [{"id": row[0], "family": row[1], "version": row[2]} for row in VIDEO_MODELS]


def seed_video_models(session: Session) -> int:
    provider = session.scalar(select(Provider).where(Provider.adapter_key == "meaicc_video"))
    if provider is None:
        provider = Provider(
            name="MEAICC",
            adapter_key="meaicc_video",
            base_url="https://api.meaicc.com",
            credentials_encrypted="",
            is_active=False,
            request_config={
                "timeout_seconds": 60,
                "poll_interval_seconds": 60,
                "task_timeout_seconds": 21600,
            },
        )
        session.add(provider)
        session.flush()
    count = 0
    for (
        public_id,
        family,
        version,
        resolution,
        minimum,
        maximum,
        unit,
        amount,
        wide,
    ) in VIDEO_MODELS:
        if session.scalar(select(Model.id).where(Model.public_id == public_id)) is not None:
            continue
        is_25 = family == "seedance-2.5"
        model = Model(
            public_id=public_id,
            display_name=f"{public_id}{f' · {version}' if version else ''}",
            media_type="video",
            provider_id=provider.id,
            upstream_model_id=public_id,
            pricing_dimensions=[],
            is_active=False,
            capabilities={
                "family": family,
                "version": version,
                "resolutions": [resolution],
                "aspect_ratios": ["1:1", "16:9", "9:16"] + (["4:3", "3:4", "21:9"] if wide else []),
                "min_seconds": str(minimum),
                "max_seconds": str(maximum),
                "max_reference_images": 30 if is_25 else 9,
                "max_reference_videos": 10 if is_25 else 3,
                "max_reference_audios": 10 if is_25 else 3,
                "supports_first_frame": True,
                "supports_last_frame": True,
                "defaults": {"seconds": "10", "resolution": resolution, "aspect_ratio": "16:9"},
            },
            prices=[
                ModelPrice(
                    variant={},
                    sale_unit=unit,
                    cost_unit=unit,
                    sale_unit_price=Decimal(amount),
                    cost_unit_price=Decimal(amount),
                )
            ],
        )
        session.add(model)
        count += 1
    session.commit()
    return count
