from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, and_, or_, desc
from sqlalchemy.dialects.postgresql import insert as pg_insert
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timedelta, timezone

from models.database import (
    Project, SourceConfig, RawPost, EnrichedPost,
    SafetySignal, CanvasState, PIIQueue, AuditLog,
    GlobalSource, ProjectGlobalSource,
    SignalSeverity, TriageAction, PIIReviewAction, SourceLatency
)
from models.schemas import ProjectCreate, ProjectUpdate, SourceConfigCreate, SourceConfigUpdate


# ─── Projects ─────────────────────────────────────────────────────────────────

async def create_project(db: AsyncSession, data: ProjectCreate) -> Project:
    project = Project(
        name=data.name,
        description=data.description,
        keywords=data.keywords,
        sources=[],
        alert_rules=data.alert_rules,
        date_from=data.date_from,
        date_to=data.date_to,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


async def get_project(db: AsyncSession, project_id: UUID) -> Optional[Project]:
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def list_projects(db: AsyncSession) -> List[Project]:
    result = await db.execute(
        select(Project).where(Project.is_active == True).order_by(desc(Project.created_at))
    )
    return list(result.scalars().all())


async def update_project(db: AsyncSession, project_id: UUID, data: ProjectUpdate) -> Optional[Project]:
    project = await get_project(db, project_id)
    if not project:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    await db.flush()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project_id: UUID) -> bool:
    project = await get_project(db, project_id)
    if not project:
        return False
    project.is_active = False
    await db.flush()
    return True


async def get_project_post_count(db: AsyncSession, project_id: UUID) -> int:
    result = await db.execute(
        select(func.count(RawPost.id)).where(RawPost.project_id == project_id)
    )
    return result.scalar_one() or 0


async def get_project_signal_count(db: AsyncSession, project_id: UUID) -> int:
    result = await db.execute(
        select(func.count(SafetySignal.id)).where(SafetySignal.project_id == project_id)
    )
    return result.scalar_one() or 0


# ─── Source Configs ───────────────────────────────────────────────────────────

async def create_source_config(db: AsyncSession, data: SourceConfigCreate) -> SourceConfig:
    config = SourceConfig(**data.model_dump())
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return config


async def list_source_configs(db: AsyncSession, project_id: UUID) -> List[SourceConfig]:
    result = await db.execute(
        select(SourceConfig).where(SourceConfig.project_id == project_id)
    )
    return list(result.scalars().all())


async def get_source_config(db: AsyncSession, source_id: UUID) -> Optional[SourceConfig]:
    result = await db.execute(select(SourceConfig).where(SourceConfig.id == source_id))
    return result.scalar_one_or_none()


async def update_source_config(db: AsyncSession, source_id: UUID, data: SourceConfigUpdate) -> Optional[SourceConfig]:
    config = await get_source_config(db, source_id)
    if not config:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(config, field, value)
    await db.flush()
    await db.refresh(config)
    return config


async def update_source_last_run(db: AsyncSession, source_id: UUID, posts_fetched: int):
    await db.execute(
        update(SourceConfig)
        .where(SourceConfig.id == source_id)
        .values(last_run=datetime.now(timezone.utc), posts_per_hour=float(posts_fetched))
    )


# ─── Raw Posts ────────────────────────────────────────────────────────────────

async def insert_raw_post(db: AsyncSession, **kwargs) -> RawPost:
    post = RawPost(**kwargs)
    db.add(post)
    await db.flush()
    await db.refresh(post)
    return post


async def bulk_insert_raw_posts(db: AsyncSession, posts: List[dict]) -> int:
    if not posts:
        return 0
    stmt = pg_insert(RawPost).values(posts).on_conflict_do_nothing()
    result = await db.execute(stmt)
    return result.rowcount


async def get_unprocessed_posts(db: AsyncSession, project_id: UUID, limit: int = 100) -> List[RawPost]:
    # FOR UPDATE SKIP LOCKED ensures concurrent pipeline workers claim disjoint batches
    result = await db.execute(
        select(RawPost)
        .where(and_(RawPost.project_id == project_id, RawPost.processed == False))
        .order_by(RawPost.timestamp.desc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


async def list_raw_posts(
    db: AsyncSession,
    project_id: UUID,
    source: Optional[str] = None,
    keyword: Optional[str] = None,
    processed: Optional[bool] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[List[RawPost], int]:
    filters = [RawPost.project_id == project_id]
    if source:
        filters.append(RawPost.source == source)
    if keyword:
        filters.append(RawPost.keyword == keyword)
    if processed is not None:
        filters.append(RawPost.processed == processed)
    if date_from:
        filters.append(RawPost.timestamp >= date_from)
    if date_to:
        filters.append(RawPost.timestamp <= date_to)

    count_result = await db.execute(
        select(func.count(RawPost.id)).where(and_(*filters))
    )
    total = count_result.scalar_one() or 0

    result = await db.execute(
        select(RawPost)
        .where(and_(*filters))
        .order_by(desc(RawPost.timestamp))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def mark_post_processed(db: AsyncSession, post_id: UUID):
    await db.execute(
        update(RawPost).where(RawPost.id == post_id).values(processed=True)
    )


# ─── Safety Signals ───────────────────────────────────────────────────────────

async def list_safety_signals(
    db: AsyncSession,
    project_id: UUID,
    severity: Optional[SignalSeverity] = None,
    drug: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[List[SafetySignal], int]:
    filters = [SafetySignal.project_id == project_id]
    if severity:
        filters.append(SafetySignal.severity == severity)
    if drug:
        filters.append(SafetySignal.drug.ilike(f"%{drug}%"))
    if date_from:
        filters.append(SafetySignal.created_at >= date_from)
    if date_to:
        filters.append(SafetySignal.created_at <= date_to)

    count_result = await db.execute(
        select(func.count(SafetySignal.id)).where(and_(*filters))
    )
    total = count_result.scalar_one() or 0

    result = await db.execute(
        select(SafetySignal)
        .where(and_(*filters))
        .order_by(desc(SafetySignal.confidence))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def triage_signal(
    db: AsyncSession,
    signal_id: UUID,
    action: TriageAction,
    rationale: Optional[str] = None,
    ai_result: Optional[dict] = None,
    user_id: Optional[str] = "analyst",
) -> Optional[SafetySignal]:
    result = await db.execute(select(SafetySignal).where(SafetySignal.id == signal_id))
    signal = result.scalar_one_or_none()
    if not signal:
        return None
    signal.triage_action = action
    signal.triage_rationale = rationale
    signal.triage_ai_result = ai_result
    signal.triaged_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=user_id,
        action="triage_signal",
        resource_type="safety_signal",
        resource_id=str(signal_id),
        query_params={"action": action.value},
    ))
    await db.flush()
    await db.refresh(signal)
    return signal


# ─── Dashboard Stats ──────────────────────────────────────────────────────────

async def get_dashboard_stats(db: AsyncSession, project_id: UUID) -> dict:
    total_posts_r = await db.execute(
        select(func.count(RawPost.id)).where(RawPost.project_id == project_id)
    )
    total_posts = total_posts_r.scalar_one() or 0

    severity_counts = {}
    for sev in [SignalSeverity.HIGH, SignalSeverity.MED, SignalSeverity.LOW]:
        r = await db.execute(
            select(func.count(SafetySignal.id)).where(
                and_(SafetySignal.project_id == project_id, SafetySignal.severity == sev)
            )
        )
        severity_counts[sev.value] = r.scalar_one() or 0

    avg_sentiment_r = await db.execute(
        select(func.avg(EnrichedPost.sentiment_score)).where(EnrichedPost.project_id == project_id)
    )
    avg_sentiment = float(avg_sentiment_r.scalar_one() or 0.0)

    pii_depth_r = await db.execute(
        select(func.count(PIIQueue.id)).where(
            and_(PIIQueue.project_id == project_id, PIIQueue.reviewer_action == PIIReviewAction.pending)
        )
    )
    pii_depth = pii_depth_r.scalar_one() or 0

    # 7-day mention volume — use text('day') to avoid asyncpg parameterizing
    # the literal differently in SELECT vs GROUP BY (PostgreSQL GroupingError)
    from sqlalchemy import text as sa_text
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    day_trunc = func.date_trunc(sa_text("'day'"), RawPost.timestamp)
    volume_result = await db.execute(
        select(
            day_trunc.label("day"),
            func.count(RawPost.id).label("count")
        )
        .where(and_(
            RawPost.project_id == project_id,
            RawPost.timestamp >= seven_days_ago,
            RawPost.timestamp <= now,
        ))
        .group_by(day_trunc)
        .order_by(day_trunc)
    )
    mention_volume_7d = [{"date": str(row.day.date()), "count": row.count} for row in volume_result]

    top_symptoms = await get_trending_symptoms(db, project_id, days=7, limit=10)
    sentiment_by_drug = await get_sentiment_by_drug(db, project_id, days=30)

    return {
        "total_posts": total_posts,
        "signal_counts": severity_counts,
        "avg_sentiment": avg_sentiment,
        "pii_queue_depth": pii_depth,
        "mention_volume_7d": mention_volume_7d,
        "top_symptoms": top_symptoms,
        "sentiment_by_drug": sentiment_by_drug,
    }


# ─── Temporal Trend Queries ───────────────────────────────────────────────────

async def get_trending_symptoms(
    db: AsyncSession, project_id: UUID, days: int = 30, limit: int = 20
) -> List[dict]:
    from sqlalchemy import text as sa_text
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            SafetySignal.symptom,
            SafetySignal.severity,
            func.count(SafetySignal.id).label("count"),
        )
        .where(and_(SafetySignal.project_id == project_id, SafetySignal.created_at >= cutoff))
        .group_by(SafetySignal.symptom, SafetySignal.severity)
        .order_by(desc(func.count(SafetySignal.id)))
        .limit(limit)
    )
    return [{"symptom": r.symptom, "severity": r.severity, "count": r.count} for r in result]


async def get_symptom_trends_over_time(
    db: AsyncSession, project_id: UUID, days: int = 30, top_n: int = 10
) -> List[dict]:
    """Daily signal counts per symptom, for the top_n most frequent symptoms."""
    from sqlalchemy import text as sa_text
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get top symptoms first
    top = await get_trending_symptoms(db, project_id, days=days, limit=top_n)
    if not top:
        return []
    top_symptoms = [r["symptom"] for r in top]

    day_trunc = func.date_trunc(sa_text("'day'"), SafetySignal.created_at)
    result = await db.execute(
        select(
            SafetySignal.symptom,
            day_trunc.label("day"),
            func.count(SafetySignal.id).label("count"),
        )
        .where(and_(
            SafetySignal.project_id == project_id,
            SafetySignal.created_at >= cutoff,
            SafetySignal.symptom.in_(top_symptoms),
        ))
        .group_by(SafetySignal.symptom, day_trunc)
        .order_by(SafetySignal.symptom, day_trunc)
    )
    rows = result.all()

    # Group by symptom → [{symptom, daily: [{date, count}]}]
    grouped: dict[str, list] = {s: [] for s in top_symptoms}
    for symptom, day, count in rows:
        grouped[symptom].append({"date": str(day.date()), "count": count, "value": None})

    return [{"entity": sym, "daily": grouped[sym]} for sym in top_symptoms if grouped[sym]]


async def get_sentiment_over_time(
    db: AsyncSession, project_id: UUID, days: int = 30
) -> List[dict]:
    from sqlalchemy import text as sa_text
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    day_trunc = func.date_trunc(sa_text("'day'"), EnrichedPost.processed_at)
    result = await db.execute(
        select(
            day_trunc.label("day"),
            func.avg(EnrichedPost.sentiment_score).label("avg_sentiment"),
            func.count(EnrichedPost.id).label("count"),
        )
        .where(and_(EnrichedPost.project_id == project_id, EnrichedPost.processed_at >= cutoff))
        .group_by(day_trunc)
        .order_by(day_trunc)
    )
    return [
        {"date": str(r.day.date()), "count": r.count, "value": round(float(r.avg_sentiment or 0.0), 3)}
        for r in result
    ]


async def get_entity_volume_over_time(
    db: AsyncSession, project_id: UUID, entity_type: str = "drug", days: int = 30
) -> List[dict]:
    """Daily count of posts that mention at least one entity of the given type."""
    from sqlalchemy import text as sa_text
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    col = EnrichedPost.drugs if entity_type == "drug" else EnrichedPost.conditions
    day_trunc = func.date_trunc(sa_text("'day'"), EnrichedPost.processed_at)
    result = await db.execute(
        select(
            day_trunc.label("day"),
            func.count(EnrichedPost.id).label("count"),
        )
        .where(and_(
            EnrichedPost.project_id == project_id,
            EnrichedPost.processed_at >= cutoff,
            func.array_length(col, 1) > 0,
        ))
        .group_by(day_trunc)
        .order_by(day_trunc)
    )
    return [{"date": str(r.day.date()), "count": r.count, "value": None} for r in result]


async def get_sentiment_by_drug(
    db: AsyncSession, project_id: UUID, days: int = 30
) -> dict:
    """Aggregate avg sentiment score per drug from entity_sentiment JSONB."""
    from sqlalchemy import text as sa_text
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(EnrichedPost.entity_sentiment, EnrichedPost.sentiment_score)
        .where(and_(
            EnrichedPost.project_id == project_id,
            EnrichedPost.processed_at >= cutoff,
            EnrichedPost.entity_sentiment != None,
        ))
    )
    rows = result.all()

    # Accumulate per drug: {drug: [scores]}
    drug_scores: dict[str, list[float]] = {}
    for entity_sentiment, post_score in rows:
        if not entity_sentiment:
            continue
        for entity, score in entity_sentiment.items():
            if entity not in drug_scores:
                drug_scores[entity] = []
            drug_scores[entity].append(float(score))

    return {
        drug: round(sum(scores) / len(scores), 3)
        for drug, scores in drug_scores.items()
        if scores
    }


# ─── Global Sources ───────────────────────────────────────────────────────────

async def list_global_sources(db: AsyncSession) -> List[GlobalSource]:
    result = await db.execute(
        select(GlobalSource).where(GlobalSource.is_active == True).order_by(GlobalSource.reliability_tier, GlobalSource.name)
    )
    return list(result.scalars().all())


async def get_global_source_by_domain(db: AsyncSession, domain: str) -> Optional[GlobalSource]:
    result = await db.execute(select(GlobalSource).where(GlobalSource.domain == domain))
    return result.scalar_one_or_none()


async def add_global_source(
    db: AsyncSession,
    domain: str,
    name: str,
    source_type: str,
    url: str,
    feed_url: Optional[str] = None,
    scraper_config: Optional[dict] = None,
    reliability_tier: int = 2,
    supports_date_range: bool = False,
) -> GlobalSource:
    existing = await get_global_source_by_domain(db, domain)
    if existing:
        return existing
    source = GlobalSource(
        domain=domain,
        name=name,
        source_type=source_type,
        url=url,
        feed_url=feed_url,
        scraper_config=scraper_config or {},
        reliability_tier=reliability_tier,
        supports_date_range=supports_date_range,
    )
    db.add(source)
    await db.flush()
    await db.refresh(source)
    return source


async def toggle_global_source(db: AsyncSession, source_id: UUID, enabled: bool) -> Optional[GlobalSource]:
    result = await db.execute(select(GlobalSource).where(GlobalSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        return None
    source.is_active = enabled
    await db.flush()
    await db.refresh(source)
    return source


async def delete_global_source(db: AsyncSession, source_id: UUID) -> bool:
    result = await db.execute(select(GlobalSource).where(GlobalSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        return False
    db.delete(source)
    await db.flush()
    return True


async def link_project_to_global_source(
    db: AsyncSession,
    project_id: UUID,
    global_source_id: UUID,
    keyword: str,
    latency: SourceLatency = SourceLatency.daily,
) -> None:
    stmt = pg_insert(ProjectGlobalSource).values(
        project_id=project_id,
        global_source_id=global_source_id,
        keyword=keyword,
        latency=latency,
        enabled=True,
    ).on_conflict_do_nothing()
    await db.execute(stmt)


async def get_project_global_source_configs(
    db: AsyncSession, project_id: UUID, date_range_only: bool = False
) -> List[tuple]:
    """Returns list of (GlobalSource, keyword, latency) for a project.

    date_range_only=True filters to sources that support server-side since/until (for batch scrapes).
    """
    filters = [
        ProjectGlobalSource.project_id == project_id,
        ProjectGlobalSource.enabled == True,
        GlobalSource.is_active == True,
    ]
    if date_range_only:
        filters.append(GlobalSource.supports_date_range == True)
    result = await db.execute(
        select(GlobalSource, ProjectGlobalSource.keyword, ProjectGlobalSource.latency)
        .join(ProjectGlobalSource, ProjectGlobalSource.global_source_id == GlobalSource.id)
        .where(*filters)
    )
    return result.all()


async def update_global_source_stats(db: AsyncSession, source_id: UUID, posts_fetched: int) -> None:
    from datetime import timezone
    await db.execute(
        update(GlobalSource)
        .where(GlobalSource.id == source_id)
        .values(
            total_posts_pulled=GlobalSource.total_posts_pulled + posts_fetched,
            last_successful_run=datetime.now(timezone.utc),
        )
    )


# ─── Canvas ───────────────────────────────────────────────────────────────────

async def get_or_create_canvas(db: AsyncSession, project_id: UUID) -> CanvasState:
    result = await db.execute(select(CanvasState).where(CanvasState.project_id == project_id))
    canvas = result.scalar_one_or_none()
    if not canvas:
        canvas = CanvasState(project_id=project_id, cards=[])
        db.add(canvas)
        await db.flush()
        await db.refresh(canvas)
    return canvas


async def update_canvas(db: AsyncSession, project_id: UUID, cards: list) -> CanvasState:
    canvas = await get_or_create_canvas(db, project_id)
    canvas.cards = cards
    await db.flush()
    await db.refresh(canvas)
    return canvas
