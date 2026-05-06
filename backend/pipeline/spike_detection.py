"""
Z-score spike detection.
Per drug-symptom pair: rolling 30-day mean + std. Z > 2.5 = spike alert.
Runs as a post-batch background job after each pipeline run.
"""
import logging
import math
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from models.database import SafetySignal, SignalSeverity

logger = logging.getLogger(__name__)

Z_THRESHOLD = 2.5
ROLLING_DAYS = 30


async def run_spike_detection(db: AsyncSession, project_id) -> list[dict]:
    """
    Compute Z-scores for all drug-symptom pairs in the last 30 days.
    Returns list of spike events above threshold.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=ROLLING_DAYS)

    # Fetch daily counts per (drug, symptom) pair
    # Use text('day') to avoid asyncpg parameterizing the literal differently
    # in SELECT vs GROUP BY, which causes PostgreSQL GroupingError
    day_trunc = func.date_trunc(text("'day'"), SafetySignal.created_at)
    result = await db.execute(
        select(
            SafetySignal.drug,
            SafetySignal.symptom,
            day_trunc.label("day"),
            func.count(SafetySignal.id).label("count"),
        )
        .where(and_(
            SafetySignal.project_id == project_id,
            SafetySignal.created_at >= window_start,
        ))
        .group_by(SafetySignal.drug, SafetySignal.symptom, day_trunc)
        .order_by(SafetySignal.drug, SafetySignal.symptom, day_trunc)
    )
    rows = result.all()

    # Group by (drug, symptom)
    pair_daily: dict[tuple, list[int]] = defaultdict(list)
    pair_dates: dict[tuple, list] = defaultdict(list)
    for drug, symptom, day, count in rows:
        pair_daily[(drug, symptom)].append(count)
        pair_dates[(drug, symptom)].append(day)

    spikes = []
    for (drug, symptom), counts in pair_daily.items():
        if len(counts) < 3:
            continue  # not enough data for Z-score

        # Today's count is the last entry
        today_count = counts[-1]
        history = counts[:-1]

        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / len(history)
        std = math.sqrt(variance) if variance > 0 else 0.0

        if std == 0:
            continue

        z_score = (today_count - mean) / std
        if z_score >= Z_THRESHOLD:
            spikes.append({
                "drug": drug,
                "symptom": symptom,
                "z_score": round(z_score, 2),
                "today_count": today_count,
                "baseline_mean": round(mean, 2),
                "baseline_std": round(std, 2),
                "date": pair_dates[(drug, symptom)][-1].isoformat() if hasattr(pair_dates[(drug, symptom)][-1], "isoformat") else str(pair_dates[(drug, symptom)][-1]),
            })
            logger.info(f"Spike detected: {drug} + {symptom} Z={z_score:.2f} (count={today_count}, mean={mean:.2f})")

    return sorted(spikes, key=lambda x: x["z_score"], reverse=True)
