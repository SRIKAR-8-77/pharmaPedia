"""
Drug Knowledge Base API — RxNorm + OpenFDA label context.
Provides per-drug intelligence for the signal cards and knowledge panel.
"""
import logging
from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from sqlalchemy import select, func, and_

from models.database import get_db, SafetySignal, SignalSeverity
from knowledge import rxnorm, openfda

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/drug/{drug_name}")
async def drug_context(drug_name: str, db: AsyncSession = Depends(get_db)):
    """
    Full drug intelligence panel:
      - RxNorm canonical name + CUI
      - FDA approved label sections (adverse reactions, warnings, boxed warning)
      - Signal statistics from our own monitoring DB
    """
    # Parallel-ish: run both fetches (async)
    rxnorm_info = await rxnorm.lookup_async(drug_name)
    label = await openfda.fetch_label_async(drug_name)

    # Signal stats from DB
    signal_counts: dict = {}
    for sev in SignalSeverity:
        count = (await db.execute(
            select(func.count(SafetySignal.id)).where(
                and_(SafetySignal.drug.ilike(f"%{drug_name}%"), SafetySignal.severity == sev)
            )
        )).scalar_one() or 0
        signal_counts[sev.value] = count

    # Novel signals — where fda_known = false (stored in triage_ai_result JSONB)
    novel_count = (await db.execute(
        select(func.count(SafetySignal.id)).where(
            and_(
                SafetySignal.drug.ilike(f"%{drug_name}%"),
                SafetySignal.triage_ai_result["fda_known"].astext == "false",
            )
        )
    )).scalar_one() or 0

    return {
        "drug_name": drug_name,
        "rxnorm": rxnorm_info,
        "fda_label": {
            "brand_name": label.get("brand_name"),
            "generic_name": label.get("generic_name"),
            "adverse_reactions_excerpt": (label.get("adverse_reactions") or "")[:800],
            "boxed_warning": label.get("boxed_warning", ""),
            "has_boxed_warning": bool(label.get("boxed_warning")),
        } if label else None,
        "signal_stats": {
            **signal_counts,
            "total": sum(signal_counts.values()),
            "novel_signals": novel_count,
        },
    }


@router.get("/fda-check")
async def fda_check(drug: str, symptom: str):
    """Quick check: is this symptom in the FDA label for this drug?"""
    known, excerpt = openfda.is_known_side_effect(drug, symptom)
    return {"drug": drug, "symptom": symptom, "known_to_fda": known, "excerpt": excerpt}
