"""
Admin API routes — Phase 5 implementation.
Phase 1: source config CRUD and PII queue endpoints are wired;
         source discovery agent and pipeline health are stubs.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID
import math

from models.database import get_db, PIIQueue, PIIReviewAction, SourceConfig, AuditLog, SafetySignal, SignalSeverity, TriageAction
from models import crud, schemas

router = APIRouter()


# ─── Scraper Registry ─────────────────────────────────────────────────────────

@router.get("/scrapers")
async def list_scrapers():
    """Return all registered scraper types with tier and reliability metadata."""
    from scrapers.registry import list_registered_scrapers
    return {"registered": list_registered_scrapers()}


# ─── Source Configs ───────────────────────────────────────────────────────────

@router.get("/sources", response_model=list[schemas.SourceConfigResponse])
async def list_all_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SourceConfig))
    return [schemas.SourceConfigResponse.model_validate(s) for s in result.scalars().all()]


@router.post("/sources", response_model=schemas.SourceConfigResponse, status_code=201)
async def create_source(data: schemas.SourceConfigCreate, db: AsyncSession = Depends(get_db)):
    config = await crud.create_source_config(db, data)
    return schemas.SourceConfigResponse.model_validate(config)


@router.patch("/sources/{source_id}", response_model=schemas.SourceConfigResponse)
async def update_source(source_id: UUID, data: schemas.SourceConfigUpdate, db: AsyncSession = Depends(get_db)):
    config = await crud.update_source_config(db, source_id, data)
    if not config:
        raise HTTPException(status_code=404, detail="Source not found")
    return schemas.SourceConfigResponse.model_validate(config)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(source_id: UUID, db: AsyncSession = Depends(get_db)):
    config = await crud.get_source_config(db, source_id)
    if not config:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(config)
    await db.commit()


# ─── Source Discovery Agent ───────────────────────────────────────────────────

@router.post("/discover")
async def discover_sources(payload: dict, db: AsyncSession = Depends(get_db)):
    """
    Run the source discovery agent for a keyword.
    Returns structured results — does NOT auto-persist anything.
    Use POST /global-sources/add-confirmed or /global-sources/add-custom to add a source.
    """
    keyword = payload.get("keyword", "")
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword is required")

    # Load existing domains so agent can classify already-tracked sources
    global_sources = await crud.list_global_sources(db)
    existing_domains = {gs.domain for gs in global_sources}

    from agents.source_discovery import discover
    results = await discover(keyword, existing_domains)

    return {"keyword": keyword, **results}


# ─── Signal Review Queue ──────────────────────────────────────────────────────

@router.get("/signal-review", response_model=schemas.PaginatedResponse)
async def list_signal_review(
    severity: Optional[str] = Query(None, description="Filter by severity: HIGH, MED, LOW"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Return all pending-triage HIGH/MED signals across all projects.
    Used by the pharmacovigilance analyst review queue in the Admin panel.
    """
    from sqlalchemy import and_, func

    if severity:
        try:
            severities = [SignalSeverity(severity)]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
    else:
        severities = [SignalSeverity.HIGH, SignalSeverity.MED]

    filters = [
        SafetySignal.triage_action == TriageAction.pending,
        SafetySignal.severity.in_(severities),
    ]

    count_r = await db.execute(select(func.count(SafetySignal.id)).where(and_(*filters)))
    total = count_r.scalar_one() or 0

    result = await db.execute(
        select(SafetySignal)
        .where(and_(*filters))
        .order_by(SafetySignal.severity.desc(), SafetySignal.confidence.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    signals = result.scalars().all()

    return schemas.PaginatedResponse(
        items=[schemas.SafetySignalResponse.model_validate(s) for s in signals],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/signal-review/counts")
async def signal_review_counts(db: AsyncSession = Depends(get_db)):
    """Badge counts for the Signal Review tab header."""
    from sqlalchemy import and_, func
    counts = {}
    for sev in [SignalSeverity.HIGH, SignalSeverity.MED]:
        r = await db.execute(
            select(func.count(SafetySignal.id)).where(
                and_(SafetySignal.triage_action == TriageAction.pending, SafetySignal.severity == sev)
            )
        )
        counts[sev.value] = r.scalar_one() or 0
    return counts


# ─── PII Queue ────────────────────────────────────────────────────────────────

@router.get("/pii-queue", response_model=schemas.PaginatedResponse)
async def list_pii_queue(
    pii_type: Optional[str] = Query(None),
    project_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import and_, func
    filters = [PIIQueue.reviewer_action == PIIReviewAction.pending]
    if pii_type:
        filters.append(PIIQueue.pii_types.any(pii_type))
    if project_id:
        filters.append(PIIQueue.project_id == project_id)

    count_r = await db.execute(select(func.count(PIIQueue.id)).where(and_(*filters)))
    total = count_r.scalar_one() or 0

    result = await db.execute(
        select(PIIQueue).where(and_(*filters))
        .offset((page - 1) * page_size).limit(page_size)
    )
    items = result.scalars().all()
    return schemas.PaginatedResponse(
        items=[schemas.PIIQueueResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.patch("/pii-queue/{item_id}", response_model=schemas.PIIQueueResponse)
async def review_pii_item(item_id: UUID, data: schemas.PIIReviewUpdate, db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone
    result = await db.execute(select(PIIQueue).where(PIIQueue.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="PII queue item not found")
    item.reviewer_action = data.reviewer_action
    item.reviewed_by = data.reviewed_by
    item.reviewed_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=data.reviewed_by,
        action="pii_review",
        resource_type="pii_queue",
        resource_id=str(item_id),
        query_params={"action": data.reviewer_action.value},
    ))
    await db.flush()
    await db.refresh(item)
    return schemas.PIIQueueResponse.model_validate(item)


# ─── Pipeline Health ──────────────────────────────────────────────────────────

@router.get("/pipeline/health")
async def pipeline_health(db: AsyncSession = Depends(get_db)):
    """Returns per-source health stats for the admin pipeline health screen."""
    result = await db.execute(select(SourceConfig))
    sources = result.scalars().all()
    return {
        "sources": [
            {
                "id": str(s.id),
                "name": s.name,
                "source_type": s.source_type,
                "status": s.status.value,
                "posts_per_hour": s.posts_per_hour,
                "last_run": s.last_run.isoformat() if s.last_run else None,
                "error_count": s.error_count,
                "enabled": s.enabled,
            }
            for s in sources
        ]
    }


# ─── Audit Log ────────────────────────────────────────────────────────────────

@router.get("/audit-log")
async def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func, desc
    count_r = await db.execute(select(func.count(AuditLog.id)))
    total = count_r.scalar_one() or 0
    result = await db.execute(
        select(AuditLog).order_by(desc(AuditLog.timestamp))
        .offset((page - 1) * page_size).limit(page_size)
    )
    logs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(l.id), "action": l.action, "user_id": l.user_id,
                "resource_type": l.resource_type, "resource_id": l.resource_id,
                "timestamp": l.timestamp.isoformat(),
            }
            for l in logs
        ],
        "total": total, "page": page, "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }
