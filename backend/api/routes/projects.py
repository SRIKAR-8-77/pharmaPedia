from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, distinct
from uuid import UUID
from datetime import datetime, timezone

from models.database import get_db, SourceLatency, SourceStatus, GlobalSource, ProjectGlobalSource
from models import crud, schemas
from tasks.scrape_tasks import scrape_project_now

router = APIRouter()


@router.post("", response_model=schemas.ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(data: schemas.ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = await crud.create_project(db, data)

    # Link keywords to selected global sources (or all active sources if none specified)
    all_sources = await crud.list_global_sources(db)
    selected_ids = set(data.selected_source_ids) if data.selected_source_ids else None
    sources_to_link = [gs for gs in all_sources if selected_ids is None or gs.id in selected_ids]
    for gs in sources_to_link:
        latency = SourceLatency.realtime if gs.source_type == "reddit" else SourceLatency.daily
        if gs.source_type == "pubmed":
            latency = SourceLatency.weekly
        for keyword in project.keywords:
            await crud.link_project_to_global_source(db, project.id, gs.id, keyword, latency)

    await db.commit()

    # If a monitoring window start is specified, kick off a historical batch scrape.
    # When date_to is null (live/ongoing), Celery beat will poll continuously after batch completes.
    if project.date_from:
        from tasks.scrape_tasks import run_batch_scrape_for_project
        run_batch_scrape_for_project.delay(str(project.id))

    post_count = await crud.get_project_post_count(db, project.id)
    signal_count = await crud.get_project_signal_count(db, project.id)
    return schemas.ProjectResponse(
        **{c.name: getattr(project, c.name) for c in project.__table__.columns},
        post_count=post_count,
        signal_count=signal_count,
    )


@router.get("", response_model=list[schemas.ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    projects = await crud.list_projects(db)
    result = []
    for p in projects:
        post_count = await crud.get_project_post_count(db, p.id)
        signal_count = await crud.get_project_signal_count(db, p.id)
        result.append(schemas.ProjectResponse(
            **{c.name: getattr(p, c.name) for c in p.__table__.columns},
            post_count=post_count,
            signal_count=signal_count,
        ))
    return result


@router.get("/{project_id}", response_model=schemas.ProjectResponse)
async def get_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    post_count = await crud.get_project_post_count(db, project_id)
    signal_count = await crud.get_project_signal_count(db, project_id)
    return schemas.ProjectResponse(
        **{c.name: getattr(project, c.name) for c in project.__table__.columns},
        post_count=post_count,
        signal_count=signal_count,
    )


@router.patch("/{project_id}", response_model=schemas.ProjectResponse)
async def update_project(project_id: UUID, data: schemas.ProjectUpdate, db: AsyncSession = Depends(get_db)):
    project = await crud.update_project(db, project_id, data)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    post_count = await crud.get_project_post_count(db, project_id)
    signal_count = await crud.get_project_signal_count(db, project_id)
    return schemas.ProjectResponse(
        **{c.name: getattr(project, c.name) for c in project.__table__.columns},
        post_count=post_count,
        signal_count=signal_count,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    deleted = await crud.delete_project(db, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("/{project_id}/pause", response_model=schemas.ProjectResponse)
async def pause_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Pause all Celery scrape + pipeline jobs for this project."""
    project = await crud.update_project(db, project_id, schemas.ProjectUpdate(is_paused=True))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    post_count = await crud.get_project_post_count(db, project_id)
    signal_count = await crud.get_project_signal_count(db, project_id)
    return schemas.ProjectResponse(
        **{c.name: getattr(project, c.name) for c in project.__table__.columns},
        post_count=post_count,
        signal_count=signal_count,
    )


@router.post("/{project_id}/resume", response_model=schemas.ProjectResponse)
async def resume_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Resume Celery scrape + pipeline jobs for this project."""
    project = await crud.update_project(db, project_id, schemas.ProjectUpdate(is_paused=False))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    post_count = await crud.get_project_post_count(db, project_id)
    signal_count = await crud.get_project_signal_count(db, project_id)
    return schemas.ProjectResponse(
        **{c.name: getattr(project, c.name) for c in project.__table__.columns},
        post_count=post_count,
        signal_count=signal_count,
    )


@router.post("/{project_id}/scrape", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrape(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Manually trigger an on-demand scrape for all sources in a project."""
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    scrape_project_now.delay(str(project_id))
    return {"message": "Scrape job queued", "project_id": str(project_id)}


@router.get("/{project_id}/sources", response_model=list[schemas.SourceConfigResponse])
async def list_sources(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # New architecture: sources come from project_global_sources → global_sources.
    # Each unique global source linked to this project is one row.
    result = await db.execute(
        select(GlobalSource, ProjectGlobalSource.latency, ProjectGlobalSource.enabled)
        .join(ProjectGlobalSource, ProjectGlobalSource.global_source_id == GlobalSource.id)
        .where(ProjectGlobalSource.project_id == project_id)
        .distinct(GlobalSource.id)
    )
    rows = result.all()

    linked = []
    seen = set()
    for gs, latency, enabled in rows:
        if gs.id in seen:
            continue
        seen.add(gs.id)
        linked.append(schemas.SourceConfigResponse(
            id=gs.id,
            project_id=project_id,
            source_type=gs.source_type,
            name=gs.name,
            url=gs.url,
            selectors={},
            scraper_config=gs.scraper_config or {},
            latency=latency or SourceLatency.daily,
            status=SourceStatus.active if gs.is_active else SourceStatus.paused,
            enabled=enabled if enabled is not None else True,
            last_run=gs.last_successful_run,
            posts_per_hour=0.0,
            error_count=0,
            created_at=gs.added_at or datetime.now(timezone.utc),
        ))

    # Also include any legacy per-project source_configs
    old_configs = await crud.list_source_configs(db, project_id)
    for cfg in old_configs:
        if cfg.id not in seen:
            linked.append(cfg)

    return linked


@router.get("/{project_id}/stats", response_model=schemas.DashboardStats)
async def get_dashboard_stats(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    stats = await crud.get_dashboard_stats(db, project_id)
    return schemas.DashboardStats(**stats)
