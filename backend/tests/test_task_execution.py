from decimal import Decimal

from sqlalchemy import select
from test_accounts import register
from test_catalog import add_model

from app.models import Asset, CreditAccount, CreditEntry, Task, TaskAsset, User
from app.providers.cangyuan import ImageOutput, ImageResult
from app.schemas import ImageGenerationRequest
from app.services.generations import create_image_task
from app.services.task_execution import process_task


class FakeAdapter:
    def submit(self, task):
        return ImageResult(state="pending", upstream_id="upstream-1", raw_status="queued")

    def query(self, upstream_id):
        return ImageResult(
            state="succeeded",
            upstream_id=upstream_id,
            raw_status="completed",
            outputs=(ImageOutput(url="https://supplier.invalid/result.png"),),
        )


def test_image_worker_transfers_result_then_settles_once(client, session, monkeypatch):
    user = register(client).json()
    account = session.get(CreditAccount, user["id"])
    account.available = Decimal("2.0000")
    _, model, _ = add_model(session)
    task = create_image_task(
        session,
        session.get(User, user["id"]),
        ImageGenerationRequest(model=model.public_id, prompt="a test image"),
    )
    session.expire_all()
    stored = session.scalar(select(Task).where(Task.task_id == task.id))
    assert stored is not None

    monkeypatch.setattr("app.services.task_execution._adapter", lambda _provider: FakeAdapter())
    monkeypatch.setattr(
        "app.services.task_execution.decode_output",
        lambda _output: (b"fake-image", "image/png"),
    )
    monkeypatch.setattr(
        "app.services.task_execution.upload_result",
        lambda *_args, **_kwargs: {
            "region": "cn-hongkong",
            "bucket": "nodepass-test",
            "object_key": f"generated/{stored.task_id}/0.png",
            "public_url": "https://image.nodepass.net/generated/result.png",
            "content_type": "image/png",
            "byte_size": 10,
        },
    )

    process_task(session, stored)
    session.expire_all()
    stored = session.scalar(select(Task).where(Task.task_id == task.id))
    assert stored.status == "pending"
    assert stored.upstream_task_id == "upstream-1"

    process_task(session, stored)
    session.expire_all()
    stored = session.scalar(select(Task).where(Task.task_id == task.id))
    account = session.get(CreditAccount, user["id"])
    assert stored.status == "succeeded"
    assert stored.billing_status == "settled"
    assert account.available == Decimal("0.7700")
    assert account.frozen == Decimal("0.0000")
    assert session.scalar(select(CreditEntry).where(CreditEntry.entry_type == "settle")) is not None
    assert session.scalar(select(Asset)) is not None
    assert session.scalar(select(TaskAsset)) is not None
