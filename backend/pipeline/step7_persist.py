"""
Step 7 — Atomic persist of enriched post + safety signals to PostgreSQL.
Publishes HIGH signals to Redis pub/sub for real-time WebSocket delivery.
"""
import json
import logging
from uuid import UUID
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update as sa_update

from models.database import RawPost, EnrichedPost, SafetySignal, PIIQueue, SignalSeverity, TriageAction, PIIReviewAction
from config import settings

logger = logging.getLogger(__name__)


async def persist_enriched(
    db: AsyncSession,
    raw_post: RawPost,
    clean_text: str,
    language: str,
    pii_result,
    entity_result,
    sentiment_result,
    signal_result,
    relevance_result,
) -> EnrichedPost | None:
    """
    Step 7 — Atomically persist enriched post and safety signals.
    If HIGH signal detected, publishes to Redis for live dashboard push.
    Returns None if post was skipped (PII held).
    """
    try:
        # If PII found — insert to pii_queue and skip enrichment
        if pii_result.has_pii:
            pii_item = PIIQueue(
                raw_post_id=raw_post.id,
                project_id=raw_post.project_id,
                pii_types=pii_result.pii_types,
                original_text=pii_result.original_text,
                redacted_text=pii_result.redacted_text,
                pii_spans=pii_result.pii_spans,
                reviewer_action=PIIReviewAction.pending,
            )
            db.add(pii_item)
            # Mark raw post as processed so it's not re-run
            await db.execute(
                sa_update(RawPost).where(RawPost.id == raw_post.id).values(processed=True)
            )
            await db.flush()
            return None

        # Determine severity enum
        severity_enum = None
        if signal_result.severity:
            try:
                severity_enum = SignalSeverity(signal_result.severity)
            except ValueError:
                pass

        # Insert enriched post
        enriched = EnrichedPost(
            raw_post_id=raw_post.id,
            project_id=raw_post.project_id,
            clean_text=clean_text,
            language=language,
            has_pii=False,
            pii_types=[],
            drugs=entity_result.drugs,
            symptoms=entity_result.symptoms,
            conditions=entity_result.conditions,
            dosages=entity_result.dosages,
            negated_entities=entity_result.negated_entities,
            sentiment=sentiment_result.sentiment,
            sentiment_score=sentiment_result.score,
            entity_sentiment=sentiment_result.entity_sentiment,
            has_safety_signal=signal_result.has_safety_signal,
            safety_severity=severity_enum,
            safety_signals=[_signal_dict(s) for s in signal_result.signals],
            causality=signal_result.causality,
            meddra_terms=signal_result.meddra_terms,
            relevance_score=relevance_result.score,
            is_duplicate=relevance_result.is_duplicate,
            minhash_signature=relevance_result.minhash_signature,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(enriched)
        await db.flush()  # get enriched.id

        # Insert individual safety signal records
        for sig in signal_result.signals:
            try:
                sev = SignalSeverity(sig["severity"])
            except ValueError:
                continue
            db.add(SafetySignal(
                enriched_post_id=enriched.id,
                project_id=raw_post.project_id,
                drug=sig["drug"],
                symptom=sig["symptom"],
                severity=sev,
                meddra_term=sig.get("meddra_term"),
                meddra_code=sig.get("meddra_code"),
                causality=signal_result.causality,
                confidence=sig.get("confidence", 0.0),
                context_window=sig.get("context_window"),
                triage_action=TriageAction.pending,
                triage_ai_result={
                    "fda_known": sig.get("known_to_fda"),
                    "fda_excerpt": sig.get("fda_excerpt", ""),
                } if sig.get("known_to_fda") is not None else None,
            ))

        # Mark raw post processed
        await db.execute(
            sa_update(RawPost).where(RawPost.id == raw_post.id).values(processed=True)
        )
        await db.flush()

        # Publish HIGH signals to Redis for live dashboard
        if signal_result.severity == "HIGH":
            await _publish_signal(raw_post.project_id, enriched, signal_result)

        return enriched

    except Exception as e:
        logger.error(f"persist_enriched failed for post {raw_post.id}: {e}")
        raise


def _signal_dict(sig: dict) -> dict:
    return {
        "drug": sig.get("drug"),
        "symptom": sig.get("symptom"),
        "severity": sig.get("severity"),
        "context_window": sig.get("context_window"),
        "confidence": sig.get("confidence"),
        "meddra_term": sig.get("meddra_term"),
        "meddra_code": sig.get("meddra_code"),
        "known_to_fda": sig.get("known_to_fda"),
        "fda_excerpt": sig.get("fda_excerpt", ""),
    }


async def _publish_signal(project_id: UUID, enriched: EnrichedPost, signal_result):
    """Publish a HIGH signal to Redis pub/sub → WebSocket clients."""
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        channel = f"project:{project_id}:signals"
        payload = json.dumps({
            "type": "HIGH_SIGNAL",
            "enriched_post_id": str(enriched.id),
            "drugs": enriched.drugs,
            "symptoms": enriched.symptoms,
            "severity": signal_result.severity,
            "causality": signal_result.causality,
            "meddra_terms": signal_result.meddra_terms,
            "timestamp": enriched.processed_at.isoformat(),
        })
        await r.publish(channel, payload)
        await r.aclose()
    except Exception as e:
        logger.warning(f"Redis publish failed (non-fatal): {e}")
