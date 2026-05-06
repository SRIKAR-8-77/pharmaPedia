"""
Copilot endpoint — Phase 4 implementation.
Phase 1: returns a placeholder response so the API boots cleanly.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from models.database import get_db
from models import crud, schemas

router = APIRouter()


@router.post("/{project_id}/copilot", response_model=schemas.CopilotResponse)
async def copilot_chat(
    project_id: UUID,
    data: schemas.CopilotRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        from agents.copilot_tools import handle_copilot_message
        return await handle_copilot_message(project_id, data, db)
    except ImportError:
        return schemas.CopilotResponse(
            text_response="Copilot is being built in Phase 4. Stay tuned!",
            card=None,
            tool_used=None,
        )
