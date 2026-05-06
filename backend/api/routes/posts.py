from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from datetime import datetime
import math

from models.database import get_db
from models import crud, schemas

router = APIRouter()


@router.get("/{project_id}/raw-posts", response_model=schemas.PaginatedResponse)
async def list_raw_posts(
    project_id: UUID,
    source: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    processed: Optional[bool] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    posts, total = await crud.list_raw_posts(
        db, project_id,
        source=source,
        keyword=keyword,
        processed=processed,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return schemas.PaginatedResponse(
        items=[schemas.RawPostResponse.model_validate(p) for p in posts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/{project_id}/posts/enriched", response_model=schemas.PaginatedResponse)
async def list_enriched_posts(
    project_id: UUID,
    source: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    has_safety_signal: Optional[bool] = Query(None),
    drug: Optional[str] = Query(None),
    symptom: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    sort_by: str = Query("relevance_score"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select, and_, desc
    from models.database import EnrichedPost, RawPost, SignalSeverity

    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    filters = [EnrichedPost.project_id == project_id]
    if has_safety_signal is not None:
        filters.append(EnrichedPost.has_safety_signal == has_safety_signal)
    if severity:
        filters.append(EnrichedPost.safety_severity == SignalSeverity(severity))
    if drug:
        filters.append(EnrichedPost.drugs.any(drug))
    if symptom:
        filters.append(EnrichedPost.symptoms.any(symptom))
    if date_from:
        filters.append(EnrichedPost.processed_at >= date_from)
    if date_to:
        filters.append(EnrichedPost.processed_at <= date_to)

    from sqlalchemy import func
    count_r = await db.execute(
        select(func.count(EnrichedPost.id)).where(and_(*filters))
    )
    total = count_r.scalar_one() or 0

    sort_col = getattr(EnrichedPost, sort_by, EnrichedPost.relevance_score)
    result = await db.execute(
        select(EnrichedPost)
        .where(and_(*filters))
        .order_by(desc(sort_col))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    posts = result.scalars().all()

    import math
    return schemas.PaginatedResponse(
        items=[schemas.EnrichedPostResponse.model_validate(p) for p in posts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )
