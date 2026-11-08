from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.dependencies import ApiKeyUser, Database
from app.models import Task, TaskAsset
from app.schemas import (
    ImageGenerationRequest,
    ImageGenerationResponse,
    OpenAIModel,
    OpenAIModelList,
    QueuedImageGeneration,
)
from app.services.catalog import visible_models
from app.services.generations import create_image_task

router = APIRouter(prefix="/v1", tags=["OpenAI compatible"])


@router.get("/models", response_model=OpenAIModelList)
def list_models(user: ApiKeyUser, session: Database):
    return OpenAIModelList(
        data=[
            OpenAIModel(id=model.public_id, created=int(model.created_at.timestamp()))
            for model in session.scalars(visible_models()).all()
        ]
    )


@router.post(
    "/images/generations",
    response_model=QueuedImageGeneration,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_image_generation(payload: ImageGenerationRequest, user: ApiKeyUser, session: Database):
    return create_image_task(session, user, payload)


@router.get("/images/generations/{task_id}", response_model=ImageGenerationResponse)
def get_image_generation(task_id: UUID, user: ApiKeyUser, session: Database):
    task = session.scalar(
        select(Task)
        .options(joinedload(Task.task_assets).joinedload(TaskAsset.asset))
        .where(Task.task_id == task_id, Task.user_id == user.id)
    )
    if task is None:
        raise HTTPException(404, "Generation not found.")
    data = [
        {"url": link.asset.public_url}
        for link in sorted(task.task_assets, key=lambda item: item.position)
        if link.role == "result"
        and link.asset
        and link.asset.status == "ready"
        and link.asset.public_url
    ]
    error = None
    if task.status == "failed":
        error = {
            "message": task.error_message or "Image generation failed.",
            "type": "generation_error",
        }
    return ImageGenerationResponse(
        id=task.task_id,
        status=task.status,
        model=task.model_snapshot.get("public_id", ""),
        created=int(task.created_at.timestamp()),
        completed=int(task.completed_at.timestamp()) if task.completed_at else None,
        data=data,
        error=error,
    )
