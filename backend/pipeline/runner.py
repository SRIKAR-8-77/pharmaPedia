"""
Pipeline runner — orchestrates all 7 steps for a batch of raw posts.
Called by Celery beat every 5 minutes and via the /pipeline/run/:id API endpoint.
"""
import logging
from uuid import UUID
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal
from models.crud import get_unprocessed_posts, get_project
from pipeline.step1_clean import clean
from pipeline.step2_pii import detect_pii
from pipeline.step3_entities import extract_entities
from pipeline.step4_sentiment import analyze_sentiment
from pipeline.step5_signals import detect_signals
from pipeline.step6_relevance import score_relevance
from pipeline.step7_persist import persist_enriched
from pipeline.spike_detection import run_spike_detection

logger = logging.getLogger(__name__)

BATCH_SIZE = 100  # posts per pipeline run


@dataclass
class PipelineStats:
    total: int = 0
    processed: int = 0
    skipped_short: int = 0
    skipped_non_english: int = 0
    pii_held: int = 0
    signals_found: int = 0
    high_signals: int = 0
    duplicates: int = 0
    errors: int = 0
    spikes: list = field(default_factory=list)


async def run_pipeline(project_id: UUID, batch_size: int = BATCH_SIZE) -> PipelineStats:
    """
    Run the full 7-step NLP pipeline for all unprocessed posts of a project.
    Returns statistics about the pipeline run.
    """
    stats = PipelineStats()

    async with AsyncSessionLocal() as db:
        project = await get_project(db, project_id)
        project_keywords = project.keywords if project else []

        posts = await get_unprocessed_posts(db, project_id, limit=batch_size)
        stats.total = len(posts)

        if not posts:
            logger.info(f"No unprocessed posts for project {project_id}")
            return stats

        logger.info(f"Running pipeline on {len(posts)} posts for project {project_id}")

        for post in posts:
            try:
                async with db.begin_nested():
                    enriched = await _process_post(db, post, stats, project_keywords=project_keywords)
                    if enriched:
                        stats.processed += 1
            except Exception as e:
                err_str = str(e)
                if "UniqueViolation" in err_str or "unique constraint" in err_str.lower():
                    pass  # Another worker already processed this post — skip silently
                else:
                    logger.error(f"Pipeline error for post {post.id}: {e}")
                stats.errors += 1

        await db.commit()

        # Post-batch: Z-score spike detection
        try:
            stats.spikes = await run_spike_detection(db, project_id)
        except Exception as e:
            logger.warning(f"Spike detection failed: {e}")

    logger.info(
        f"Pipeline done: {stats.processed}/{stats.total} processed, "
        f"{stats.high_signals} HIGH signals, {stats.pii_held} PII held, "
        f"{stats.duplicates} duplicates, {len(stats.spikes)} spikes"
    )
    return stats


async def _process_post(db: AsyncSession, post, stats: PipelineStats, project_keywords: list = None):
    """Run all 7 steps for a single post. Returns EnrichedPost or None."""

    # ── Step 1: Clean ─────────────────────────────────────────────────────────
    clean_result = clean(post.text, post.title)
    if clean_result.skip:
        if clean_result.skip_reason == "too_short":
            stats.skipped_short += 1
        elif clean_result.skip_reason == "non_english":
            stats.skipped_non_english += 1
        # Mark as processed so we don't re-run it
        from sqlalchemy import update as sa_update
        from models.database import RawPost
        await db.execute(sa_update(RawPost).where(RawPost.id == post.id).values(processed=True))
        return None

    clean_text = clean_result.text
    language = clean_result.language

    # ── Step 2: PII detection ─────────────────────────────────────────────────
    pii_result = detect_pii(clean_text)

    # ── Step 3: Entity extraction ─────────────────────────────────────────────
    entity_result = extract_entities(clean_text, project_keywords=project_keywords or [])

    # ── Step 4: Sentiment ─────────────────────────────────────────────────────
    all_entities = entity_result.drugs + entity_result.symptoms
    sentiment_result = analyze_sentiment(clean_text, entities=all_entities)

    # ── Step 5: Safety signals ────────────────────────────────────────────────
    signal_result = detect_signals(
        clean_text, entity_result.drugs, entity_result.symptoms,
        project_keywords=project_keywords or [],
    )
    if signal_result.has_safety_signal:
        stats.signals_found += 1
        if signal_result.severity == "HIGH":
            stats.high_signals += 1

    # ── Step 6: Relevance scoring ─────────────────────────────────────────────
    relevance_result = score_relevance(
        text=clean_text,
        drugs=entity_result.drugs,
        symptoms=entity_result.symptoms,
        conditions=entity_result.conditions,
        has_signal=signal_result.has_safety_signal,
        severity=signal_result.severity,
        sentiment_score=sentiment_result.score,
        post_id=str(post.id),
    )
    if relevance_result.is_duplicate:
        stats.duplicates += 1

    # ── Step 7: Persist ───────────────────────────────────────────────────────
    enriched = await persist_enriched(
        db=db,
        raw_post=post,
        clean_text=clean_text,
        language=language,
        pii_result=pii_result,
        entity_result=entity_result,
        sentiment_result=sentiment_result,
        signal_result=signal_result,
        relevance_result=relevance_result,
    )

    if enriched is None and pii_result.has_pii:
        stats.pii_held += 1

    return enriched
