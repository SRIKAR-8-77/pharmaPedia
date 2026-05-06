from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from models.database import get_db
from models import crud
from tasks.pipeline_tasks import run_pipeline_for_project

router = APIRouter()


@router.get("/run/{project_id}")
async def trigger_pipeline(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Count unprocessed posts before queueing
    from sqlalchemy import select, func, and_
    from models.database import RawPost
    count_r = await db.execute(
        select(func.count(RawPost.id)).where(
            and_(RawPost.project_id == project_id, RawPost.processed == False)
        )
    )
    unprocessed = count_r.scalar_one() or 0

    run_pipeline_for_project.delay(str(project_id))
    return {"message": "Pipeline job queued", "project_id": str(project_id), "unprocessed_posts": unprocessed}
