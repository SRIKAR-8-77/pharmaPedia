from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
from datetime import datetime

import httpx
from pydantic import BaseModel

from models.database import get_db, SourceLatency
from models import crud

router = APIRouter()


class GlobalSourceResponse(BaseModel):
    id: UUID
    domain: str
    name: str
    source_type: str
    url: str
    feed_url: Optional[str]
    reliability_tier: int
    supports_date_range: bool = False
    total_posts_pulled: Optional[int] = 0
    last_successful_run: Optional[datetime]
    added_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class AddConfirmedSourceRequest(BaseModel):
    name: str
    domain: str
    source_type: str        # "rss" | "api" | "reddit"
    url: str
    feed_url: Optional[str] = None
    project_id: Optional[UUID] = None
    keyword: Optional[str] = None


class AddCustomSourceRequest(BaseModel):
    url: str                # RSS feed URL or API base URL
    name: str
    source_type: str        # "rss" | "api"
    project_id: Optional[UUID] = None
    keyword: Optional[str] = None


@router.get("", response_model=list[GlobalSourceResponse])
async def list_global_sources(db: AsyncSession = Depends(get_db)):
    """List all global sources with their pull stats."""
    return await crud.list_global_sources(db)


@router.post("/{source_id}/toggle", response_model=GlobalSourceResponse)
async def toggle_global_source(
    source_id: UUID,
    enabled: bool,
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable a global source (affects all projects that use it)."""
    source = await crud.toggle_global_source(db, source_id, enabled)
    if not source:
        raise HTTPException(status_code=404, detail="Global source not found")
    return source


@router.post("/add-confirmed", response_model=GlobalSourceResponse, status_code=status.HTTP_201_CREATED)
async def add_confirmed_source(data: AddConfirmedSourceRequest, db: AsyncSession = Depends(get_db)):
    """
    Persist a source that the discovery agent found.
    The user explicitly confirms they want to add it.
    """
    gs = await crud.add_global_source(
        db,
        domain=data.domain[:255],
        name=data.name[:255],
        source_type=data.source_type,
        url=data.url,
        feed_url=data.feed_url,
        supports_date_range=False,  # discovered RSS/API sources don't support historical range
    )
    if data.project_id and data.keyword:
        lat = SourceLatency.realtime if data.source_type == "reddit" else SourceLatency.daily
        await crud.link_project_to_global_source(db, data.project_id, gs.id, data.keyword, lat)
    await db.commit()
    await db.refresh(gs)
    return gs


@router.post("/add-custom", response_model=GlobalSourceResponse, status_code=status.HTTP_201_CREATED)
async def add_custom_source(data: AddCustomSourceRequest, db: AsyncSession = Depends(get_db)):
    """
    Add any RSS feed URL or API endpoint the user found themselves.
    A HEAD request confirms the URL is reachable before persisting.
    """
    from urllib.parse import urlparse
    domain = urlparse(data.url).netloc.lstrip("www.") or data.url[:255]

    # Quick reachability check
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            resp = await client.head(data.url)
            if resp.status_code >= 500:
                raise HTTPException(
                    status_code=400,
                    detail=f"URL returned server error ({resp.status_code}) — check the URL and try again",
                )
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Could not reach URL: {e}")

    gs = await crud.add_global_source(
        db,
        domain=domain[:255],
        name=data.name[:255],
        source_type=data.source_type,
        url=data.url,
        feed_url=data.url if data.source_type == "rss" else None,
        supports_date_range=False,
    )
    if data.project_id and data.keyword:
        lat = SourceLatency.realtime if data.source_type == "reddit" else SourceLatency.daily
        await crud.link_project_to_global_source(db, data.project_id, gs.id, data.keyword, lat)
    await db.commit()
    await db.refresh(gs)
    return gs
