"""
Pharmacovigilance Report Generator.

Generates structured PV reports from signal data — downloadable as JSON or
formatted HTML (browser-printable to PDF).

Report content follows ICH E2B-inspired structure:
  - Executive summary
  - Signal summary (HIGH/MED/LOW, novel vs known)
  - Top drug-symptom pairs
  - Data source breakdown
  - PII compliance stats
  - Recommendations
"""
import math
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from models.database import (
    get_db, Project, RawPost, EnrichedPost, SafetySignal, PIIQueue,
    AuditLog, Report, SignalSeverity, TriageAction, PIIReviewAction,
)
from models import schemas

router = APIRouter()


# ── Report generation ─────────────────────────────────────────────────────────

@router.post("/{project_id}/reports", status_code=201)
async def generate_report(
    project_id: UUID,
    days: int = Query(30, ge=1, le=365, description="Reporting period in days"),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a structured pharmacovigilance report for a project.
    Computes all metrics from the database for the specified period.
    """
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=days)

    # Post stats
    total_posts = (await db.execute(
        select(func.count(RawPost.id)).where(
            and_(RawPost.project_id == project_id, RawPost.timestamp >= period_start)
        )
    )).scalar_one() or 0

    # Source breakdown
    source_rows = await db.execute(
        select(RawPost.source, func.count(RawPost.id))
        .where(and_(RawPost.project_id == project_id, RawPost.timestamp >= period_start))
        .group_by(RawPost.source)
    )
    by_source = {row[0]: row[1] for row in source_rows.all()}

    # Signal breakdown
    signal_counts: dict = {}
    for sev in SignalSeverity:
        count = (await db.execute(
            select(func.count(SafetySignal.id)).where(
                and_(SafetySignal.project_id == project_id, SafetySignal.created_at >= period_start,
                     SafetySignal.severity == sev)
            )
        )).scalar_one() or 0
        signal_counts[sev.value] = count

    escalated = (await db.execute(
        select(func.count(SafetySignal.id)).where(
            and_(SafetySignal.project_id == project_id, SafetySignal.created_at >= period_start,
                 SafetySignal.triage_action == TriageAction.escalate)
        )
    )).scalar_one() or 0

    # Novel signals (fda_known = false in triage_ai_result)
    novel = (await db.execute(
        select(func.count(SafetySignal.id)).where(
            and_(
                SafetySignal.project_id == project_id,
                SafetySignal.created_at >= period_start,
                SafetySignal.triage_ai_result["fda_known"].astext == "false",
            )
        )
    )).scalar_one() or 0

    # Top signals by confidence
    top_rows = await db.execute(
        select(SafetySignal)
        .where(and_(SafetySignal.project_id == project_id, SafetySignal.created_at >= period_start))
        .order_by(SafetySignal.severity.desc(), SafetySignal.confidence.desc())
        .limit(10)
    )
    top_signals = [
        {
            "drug": s.drug, "symptom": s.symptom,
            "severity": s.severity.value, "confidence": s.confidence,
            "causality": s.causality, "meddra_term": s.meddra_term,
            "known_to_fda": (s.triage_ai_result or {}).get("fda_known"),
            "triage_action": s.triage_action.value,
        }
        for s in top_rows.scalars().all()
    ]

    # Sentiment stats
    sentiment_stats = (await db.execute(
        select(func.avg(EnrichedPost.sentiment_score), func.count(EnrichedPost.id))
        .where(and_(EnrichedPost.project_id == project_id, EnrichedPost.processed_at >= period_start))
    )).one()
    avg_sentiment = float(sentiment_stats[0] or 0.0)
    total_enriched = sentiment_stats[1] or 0

    # Sentiment distribution
    sent_dist: dict = {}
    for label in ["positive", "neutral", "negative"]:
        count = (await db.execute(
            select(func.count(EnrichedPost.id)).where(
                and_(EnrichedPost.project_id == project_id,
                     EnrichedPost.processed_at >= period_start,
                     EnrichedPost.sentiment == label)
            )
        )).scalar_one() or 0
        sent_dist[label] = count

    # PII stats
    pii_total = (await db.execute(
        select(func.count(PIIQueue.id)).where(
            and_(PIIQueue.project_id == project_id, PIIQueue.created_at >= period_start)
        )
    )).scalar_one() or 0
    pii_reviewed = (await db.execute(
        select(func.count(PIIQueue.id)).where(
            and_(PIIQueue.project_id == project_id,
                 PIIQueue.created_at >= period_start,
                 PIIQueue.reviewer_action != PIIReviewAction.pending)
        )
    )).scalar_one() or 0

    # Duplicates
    duplicate_count = (await db.execute(
        select(func.count(EnrichedPost.id)).where(
            and_(EnrichedPost.project_id == project_id,
                 EnrichedPost.processed_at >= period_start,
                 EnrichedPost.is_duplicate == True)
        )
    )).scalar_one() or 0

    total_signals = sum(signal_counts.values())

    # Auto-generate recommendations
    recommendations = _generate_recommendations(
        signal_counts, novel, escalated, pii_total - pii_reviewed, avg_sentiment
    )

    content = {
        "title": f"PharmaSignal Pharmacovigilance Report — {project.name}",
        "project_name": project.name,
        "project_keywords": project.keywords,
        "period": {"start": period_start.isoformat(), "end": now.isoformat(), "days": days},
        "generated_at": now.isoformat(),
        "executive_summary": _executive_summary(project, total_posts, signal_counts, novel, avg_sentiment, days),
        "signal_summary": {
            **signal_counts,
            "total": total_signals,
            "escalated": escalated,
            "novel_signals": novel,
            "known_signals": total_signals - novel,
            "pending_review": signal_counts.get("HIGH", 0) + signal_counts.get("MED", 0) - escalated,
        },
        "top_signals": top_signals,
        "data_sources": {
            "total_posts": total_posts,
            "total_enriched": total_enriched,
            "by_source": by_source,
            "duplicate_rate_pct": round(duplicate_count / max(total_enriched, 1) * 100, 1),
        },
        "sentiment_overview": {
            "average_score": round(avg_sentiment, 3),
            "distribution": sent_dist,
        },
        "pii_compliance": {
            "total_detected": pii_total,
            "reviewed": pii_reviewed,
            "pending": pii_total - pii_reviewed,
            "review_rate_pct": round(pii_reviewed / max(pii_total, 1) * 100, 1),
        },
        "recommendations": recommendations,
    }

    report = Report(
        project_id=project_id,
        period_start=period_start,
        period_end=now,
        content=content,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)

    return {
        "id": str(report.id),
        "project_id": str(report.project_id),
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "created_at": report.created_at.isoformat(),
        "content": report.content,
    }


@router.get("/{project_id}/reports")
async def list_reports(project_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Report).where(Report.project_id == project_id).order_by(desc(Report.created_at))
    )
    reports = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "project_id": str(r.project_id),
            "period_start": r.period_start.isoformat(),
            "period_end": r.period_end.isoformat(),
            "created_at": r.created_at.isoformat(),
            "signal_total": r.content.get("signal_summary", {}).get("total", 0),
            "novel_signals": r.content.get("signal_summary", {}).get("novel_signals", 0),
        }
        for r in reports
    ]


@router.get("/{project_id}/reports/{report_id}")
async def get_report(project_id: UUID, report_id: UUID, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(
        select(Report).where(and_(Report.id == report_id, Report.project_id == project_id))
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "id": str(r.id),
        "project_id": str(r.project_id),
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "created_at": r.created_at.isoformat(),
        "content": r.content,
    }


@router.get("/{project_id}/reports/{report_id}/html", response_class=HTMLResponse)
async def get_report_html(project_id: UUID, report_id: UUID, db: AsyncSession = Depends(get_db)):
    """Rendered HTML report — open in browser, use Ctrl+P to save as PDF."""
    r = (await db.execute(
        select(Report).where(and_(Report.id == report_id, Report.project_id == project_id))
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    return HTMLResponse(content=_render_html(r.content))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _executive_summary(project, total_posts: int, signal_counts: dict, novel: int, avg_sentiment: float, days: int) -> str:
    high = signal_counts.get("HIGH", 0)
    total = sum(signal_counts.values())
    sentiment_desc = "predominantly negative" if avg_sentiment < -0.3 else "mixed" if avg_sentiment < 0.1 else "generally positive"
    novel_note = f" {novel} signals were NOT previously listed in FDA-approved drug labels, warranting regulatory review." if novel > 0 else ""
    return (
        f"During the {days}-day monitoring period, PharmaSignal analyzed {total_posts} posts from "
        f"{len(project.keywords)} monitored keyword(s) ({', '.join(project.keywords)}). "
        f"{total} safety signals were detected: {high} HIGH severity, "
        f"{signal_counts.get('MED', 0)} MED, {signal_counts.get('LOW', 0)} LOW. "
        f"Social sentiment was {sentiment_desc} (avg score: {avg_sentiment:.2f}).{novel_note}"
    )


def _generate_recommendations(signal_counts: dict, novel: int, escalated: int, pii_pending: int, avg_sentiment: float) -> list:
    recs = []
    if signal_counts.get("HIGH", 0) > 0:
        recs.append({
            "priority": "HIGH",
            "action": f"Review {signal_counts['HIGH']} HIGH-severity signals in the Signal Validation Queue. "
                      f"{escalated} have been escalated to date.",
        })
    if novel > 0:
        recs.append({
            "priority": "HIGH",
            "action": f"{novel} novel signals detected (not in FDA label). Consider filing MedWatch reports "
                      f"and reviewing FAERS for corroborating cases.",
        })
    if pii_pending > 5:
        recs.append({
            "priority": "MED",
            "action": f"{pii_pending} PII items awaiting human review. Complete review to maintain GDPR compliance.",
        })
    if avg_sentiment < -0.5:
        recs.append({
            "priority": "MED",
            "action": "Average patient sentiment is strongly negative. Recommend qualitative analysis of top complaints.",
        })
    if not recs:
        recs.append({
            "priority": "LOW",
            "action": "No urgent actions identified. Continue routine monitoring.",
        })
    return recs


def _render_html(content: dict) -> str:
    """Generate a print-ready HTML report."""
    sigs = content.get("signal_summary", {})
    top = content.get("top_signals", [])
    recs = content.get("recommendations", [])
    period = content.get("period", {})

    sig_rows = ""
    for s in top:
        fda = "Known" if s.get("known_to_fda") else ("Novel" if s.get("known_to_fda") is False else "—")
        fda_color = "#56617a" if fda == "—" else ("#22c55e" if fda == "Known" else "#ef4444")
        sev_color = {"HIGH": "#ef4444", "MED": "#f59e0b", "LOW": "#3b82f6"}.get(s.get("severity", ""), "#56617a")
        sig_rows += f"""
        <tr>
          <td>{s.get('drug', '—')}</td>
          <td>{s.get('symptom', '—')}</td>
          <td style="color:{sev_color};font-weight:700">{s.get('severity', '—')}</td>
          <td>{round((s.get('confidence') or 0) * 100)}%</td>
          <td>{s.get('causality', '—')}</td>
          <td>{s.get('meddra_term') or '—'}</td>
          <td style="color:{fda_color};font-weight:600">{fda}</td>
        </tr>"""

    rec_rows = ""
    for r in recs:
        pri_color = {"HIGH": "#ef4444", "MED": "#f59e0b", "LOW": "#22c55e"}.get(r.get("priority", ""), "#56617a")
        rec_rows += f'<li><span style="color:{pri_color};font-weight:700">[{r.get("priority")}]</span> {r.get("action")}</li>'

    sources = content.get("data_sources", {}).get("by_source", {})
    src_html = " · ".join(f"<b>{k}</b>: {v}" for k, v in sources.items())

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{content.get('title', 'PV Report')}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, Arial, sans-serif; font-size: 13px; color: #1a1a2e; padding: 40px; max-width: 1000px; margin: 0 auto; }}
  h1 {{ font-size: 22px; font-weight: 800; color: #0f172a; margin-bottom: 4px; }}
  h2 {{ font-size: 15px; font-weight: 700; color: #0f172a; margin: 28px 0 10px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; }}
  .meta {{ font-size: 12px; color: #64748b; margin-bottom: 6px; }}
  .summary {{ background: #f8fafc; border-left: 4px solid #3b82f6; padding: 14px 18px; border-radius: 4px; margin: 16px 0; line-height: 1.7; }}
  .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }}
  .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center; }}
  .card-num {{ font-size: 28px; font-weight: 800; }}
  .card-lbl {{ font-size: 11px; color: #64748b; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
  th {{ background: #f1f5f9; padding: 8px 12px; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #f1f5f9; font-size: 12px; }}
  ul {{ padding-left: 20px; line-height: 2; }}
  .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; }}
  @media print {{ body {{ padding: 20px; }} }}
</style>
</head>
<body>
  <h1>{content.get('title', 'Pharmacovigilance Report')}</h1>
  <p class="meta">Period: {period.get('start', '')[:10]} → {period.get('end', '')[:10]} ({period.get('days', '?')} days)  &nbsp;|&nbsp;  Generated: {content.get('generated_at', '')[:19].replace('T', ' ')} UTC</p>
  <p class="meta">Project keywords: {', '.join(content.get('project_keywords', []))}</p>

  <h2>Executive Summary</h2>
  <div class="summary">{content.get('executive_summary', '')}</div>

  <h2>Signal Overview</h2>
  <div class="cards">
    <div class="card"><div class="card-num" style="color:#ef4444">{sigs.get('HIGH', 0)}</div><div class="card-lbl">HIGH Severity</div></div>
    <div class="card"><div class="card-num" style="color:#f59e0b">{sigs.get('MED', 0)}</div><div class="card-lbl">MED Severity</div></div>
    <div class="card"><div class="card-num" style="color:#3b82f6">{sigs.get('LOW', 0)}</div><div class="card-lbl">LOW Severity</div></div>
    <div class="card"><div class="card-num" style="color:#ef4444">{sigs.get('novel_signals', 0)}</div><div class="card-lbl">Novel Signals</div></div>
  </div>

  <h2>Top Safety Signals</h2>
  <table>
    <thead><tr><th>Drug</th><th>Symptom / Event</th><th>Severity</th><th>Confidence</th><th>Causality</th><th>MedDRA Term</th><th>FDA Label</th></tr></thead>
    <tbody>{sig_rows}</tbody>
  </table>

  <h2>Data Sources — {content.get('data_sources', {}).get('total_posts', 0)} posts analyzed</h2>
  <p style="line-height:2">{src_html}</p>
  <p style="margin-top:6px;color:#64748b">Duplicate rate: {content.get('data_sources', {}).get('duplicate_rate_pct', 0)}% &nbsp;|&nbsp;
     Avg sentiment: {content.get('sentiment_overview', {}).get('average_score', 0):.2f}</p>

  <h2>PII Compliance</h2>
  <p>PII detected: <b>{content.get('pii_compliance', {}).get('total_detected', 0)}</b> &nbsp;|&nbsp;
     Reviewed: <b>{content.get('pii_compliance', {}).get('reviewed', 0)}</b> &nbsp;|&nbsp;
     Review rate: <b>{content.get('pii_compliance', {}).get('review_rate_pct', 0)}%</b></p>

  <h2>Recommendations</h2>
  <ul>{rec_rows}</ul>

  <div class="footer">
    Generated by PharmaSignal &nbsp;|&nbsp; For regulatory and pharmacovigilance use only &nbsp;|&nbsp;
    ICH E2B-inspired format &nbsp;|&nbsp; Not a substitute for qualified pharmacovigilance review
  </div>
</body>
</html>"""
