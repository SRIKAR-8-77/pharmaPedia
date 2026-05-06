from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from datetime import datetime
import math

from models.database import get_db, SignalSeverity
from models import crud, schemas

router = APIRouter()


@router.get("/{project_id}/signals", response_model=schemas.PaginatedResponse)
async def list_signals(
    project_id: UUID,
    severity: Optional[str] = Query(None),
    drug: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sev = SignalSeverity(severity) if severity else None
    signals, total = await crud.list_safety_signals(
        db, project_id, severity=sev, drug=drug,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size,
    )
    return schemas.PaginatedResponse(
        items=[schemas.SafetySignalResponse.model_validate(s) for s in signals],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.post("/signals/{signal_id}/triage", response_model=schemas.SafetySignalResponse)
async def triage_signal(
    signal_id: UUID,
    data: schemas.SignalTriageUpdate,
    db: AsyncSession = Depends(get_db),
):
    signal = await crud.triage_signal(
        db, signal_id, data.triage_action, data.triage_rationale,
        user_id=data.reviewed_by or "analyst",
    )
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return schemas.SafetySignalResponse.model_validate(signal)


@router.post("/signals/{signal_id}/triage-ai")
async def triage_signal_with_ai(signal_id: UUID, db: AsyncSession = Depends(get_db)):
    """Trigger AI triage agent for a signal (Phase 5 — agent implementation)."""
    from sqlalchemy import select
    from models.database import SafetySignal
    result = await db.execute(select(SafetySignal).where(SafetySignal.id == signal_id))
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    try:
        from agents.alert_triage import triage_with_ai
        ai_result = await triage_with_ai(signal)
        updated = await crud.triage_signal(
            db, signal_id,
            action=schemas.TriageAction(ai_result["action"]),
            rationale=ai_result.get("rationale"),
            ai_result=ai_result,
        )
        return schemas.SafetySignalResponse.model_validate(updated)
    except ImportError:
        raise HTTPException(status_code=501, detail="AI triage agent not yet implemented (Phase 5)")


@router.get("/{project_id}/trends", response_model=schemas.TrendResponse)
async def get_trends(
    project_id: UUID,
    days: int = Query(30, ge=1, le=365),
    entity_type: str = Query("drug", pattern="^(drug|condition)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Temporal trend data for a project.
    Returns top symptoms, per-symptom daily sparklines, sentiment over time,
    and entity (drug or condition) mention volume over time.
    """
    project = await crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    top_symptoms_raw, symptom_trends_raw, sentiment_raw, volume_raw = await _gather_trends(
        db, project_id, days, entity_type
    )

    return schemas.TrendResponse(
        period_days=days,
        top_symptoms=[
            schemas.SymptomTrend(
                symptom=r["symptom"],
                count=r["count"],
                severity=r["severity"],
            )
            for r in top_symptoms_raw
        ],
        symptom_trends=[
            schemas.EntityDailyVolume(
                entity=row["entity"],
                daily=[
                    schemas.DailyDataPoint(date=d["date"], count=d["count"], value=d.get("value"))
                    for d in row["daily"]
                ],
            )
            for row in symptom_trends_raw
        ],
        sentiment_over_time=[
            schemas.DailyDataPoint(date=r["date"], count=r["count"], value=r.get("value"))
            for r in sentiment_raw
        ],
        entity_volume=[
            schemas.DailyDataPoint(date=r["date"], count=r["count"], value=None)
            for r in volume_raw
        ],
    )


async def _gather_trends(db, project_id, days, entity_type):
    """Run all 4 trend queries concurrently."""
    import asyncio
    return await asyncio.gather(
        crud.get_trending_symptoms(db, project_id, days=days, limit=20),
        crud.get_symptom_trends_over_time(db, project_id, days=days, top_n=10),
        crud.get_sentiment_over_time(db, project_id, days=days),
        crud.get_entity_volume_over_time(db, project_id, entity_type=entity_type, days=days),
    )
