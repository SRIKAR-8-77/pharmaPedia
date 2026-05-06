import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from models.database import get_db, CanvasState
from models import crud, schemas

router = APIRouter()


@router.get("/{project_id}/canvas", response_model=schemas.CanvasStateResponse)
async def get_canvas(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    canvas = await crud.get_or_create_canvas(db, project_id)
    return schemas.CanvasStateResponse.model_validate(canvas)


@router.patch("/{project_id}/canvas", response_model=schemas.CanvasStateResponse)
async def update_canvas(
    project_id: UUID,
    data: schemas.CanvasStateUpdate,
    db: AsyncSession = Depends(get_db),
):
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    canvas = await crud.update_canvas(db, project_id, data.cards)
    return schemas.CanvasStateResponse.model_validate(canvas)


@router.post("/{project_id}/canvas/share")
async def share_canvas(project_id: UUID, db: AsyncSession = Depends(get_db)):
    canvas = await crud.get_or_create_canvas(db, project_id)
    if not canvas.share_id:
        canvas.share_id = secrets.token_urlsafe(32)
        await db.flush()
        await db.refresh(canvas)
    return {"share_id": canvas.share_id, "share_url": f"/canvas/share/{canvas.share_id}"}


@router.get("/canvas/share/{share_id}", response_model=schemas.CanvasStateResponse)
async def get_shared_canvas(share_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CanvasState).where(CanvasState.share_id == share_id))
    canvas = result.scalar_one_or_none()
    if not canvas:
        raise HTTPException(status_code=404, detail="Shared canvas not found")
    return schemas.CanvasStateResponse.model_validate(canvas)
