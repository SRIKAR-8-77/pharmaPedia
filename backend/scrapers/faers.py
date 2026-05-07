"""
FDA FAERS (Adverse Event Reporting System) scraper.

Uses the FDA Open API — completely free, no authentication required.
This is Tier 1: the most reliable and highest-quality source for pharmacovigilance.

API docs: https://open.fda.gov/apis/drug/event/
Rate limit: 240 requests/min unauthenticated (sufficient for demo).
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import httpx

from scrapers.base import BaseScraper, ScrapedPost

logger = logging.getLogger(__name__)

FAERS_BASE = "https://api.fda.gov/drug/event.json"

# Map FDA reaction severity fields to human-readable context
SERIOUS_FIELDS = {
    "seriousnessdeath": "death",
    "seriousnesshospitalization": "hospitalization",
    "seriousnesslifethreatening": "life-threatening condition",
    "seriousnessdisabling": "disabling condition",
    "seriousnesscongenitalanomali": "congenital anomaly",
    "seriousnessother": "serious adverse outcome",
}

# FDA uses numeric codes for patient sex
SEX_MAP = {"1": "male", "2": "female", "0": "unknown"}


def _build_synthetic_text(report: dict, searched_drug: str = "") -> str:
    """Convert a FAERS report dict into a natural-language text for NLP processing."""
    patient = report.get("patient", {})
    drugs = patient.get("drug", [])
    reactions = patient.get("reaction", [])

    drug_names = [d.get("medicinalproduct", "").lower() for d in drugs if d.get("medicinalproduct")]
    reaction_names = [r.get("reactionmeddrapt", "") for r in reactions if r.get("reactionmeddrapt")]

    # Put the searched drug first so NLP picks it up as primary drug
    if searched_drug:
        drug_names = sorted(drug_names, key=lambda d: 0 if searched_drug.lower() in d else 1)

    # Build seriousness context
    serious_contexts = [
        label for field, label in SERIOUS_FIELDS.items()
        if str(report.get(field, "")) == "1"
    ]

    age_group = patient.get("patientagegroup", "")
    sex = SEX_MAP.get(str(patient.get("patientsex", "0")), "unknown")
    country = report.get("primarysource", {}).get("reportercountry", "unknown")
    indication = next(
        (d.get("drugindication", "") for d in drugs if d.get("drugindication")),
        ""
    )

    # Construct a readable adverse event description
    parts = []
    if drug_names:
        parts.append(f"Patient reported taking {', '.join(drug_names[:3])}")
    if indication:
        parts.append(f"for {indication.lower()}")
    if reaction_names:
        parts.append(f"and experienced: {', '.join(reaction_names[:5])}")
    if serious_contexts:
        parts.append(f"Outcome: {', '.join(serious_contexts)}")
    if age_group:
        age_labels = {"1": "neonate", "2": "infant", "3": "child", "4": "adolescent", "5": "adult", "6": "elderly"}
        parts.append(f"Patient: {age_labels.get(str(age_group), 'adult')} {sex}")
    if country and country != "US":
        parts.append(f"Report country: {country}")

    return ". ".join(parts) if parts else f"Adverse event report for {', '.join(drug_names)}"


def _parse_faers_date(date_str: str) -> datetime:
    """Parse FDA YYYYMMDD date format."""
    try:
        return datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


class FAERSScraper(BaseScraper):
    """
    Fetches real adverse event reports from FDA FAERS API.
    Tier 1 source: official, free, no authentication, no rate-limit concerns for demo.
    """
    source_type = "faers"
    reliability_tier = 1
    source_description = "FDA Adverse Event Reporting System (official API)"

    async def fetch(
        self,
        keyword: str,
        limit: int = 100,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[ScrapedPost]:
        # Date range: use since/until if provided, else fall back to lookback_days config
        end_dt = until or datetime.now(timezone.utc)
        if since:
            start_dt = since
        else:
            lookback_days = self.config.get("lookback_days", 540)  # FAERS lags ~6–12 months; need 18mo window
            start_dt = end_dt - timedelta(days=lookback_days)
        start_str = start_dt.strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")

        # Build FAERS search URL — construct manually to avoid httpx double-encoding
        # FDA FAERS uses Lucene syntax; date range brackets must be literal in the URL
        from urllib.parse import quote
        drug_quoted = quote(f'"{keyword}"', safe="")
        date_range = f"receivedate:[{start_str}+TO+{end_str}]"
        search_expr = f"patient.drug.medicinalproduct:{drug_quoted}+AND+{date_range}"

        all_posts: List[ScrapedPost] = []
        skip = 0
        batch_size = min(limit, 100)

        async with httpx.AsyncClient(timeout=20) as client:
            while len(all_posts) < limit:
                url = f"{FAERS_BASE}?search={search_expr}&limit={batch_size}&skip={skip}"
                data = None
                for attempt in range(3):
                    try:
                        resp = await client.get(url)
                        if resp.status_code == 404:
                            break
                        if resp.status_code in (429, 500, 502, 503, 504):
                            wait = 2 ** attempt
                            logger.warning(f"FAERS {resp.status_code} for '{keyword}', retry {attempt+1}/3 in {wait}s")
                            await asyncio.sleep(wait)
                            continue
                        resp.raise_for_status()
                        data = resp.json()
                        break
                    except httpx.HTTPStatusError as e:
                        logger.warning(f"FAERS API error for '{keyword}': {e.response.status_code}")
                        break
                    except Exception as e:
                        logger.error(f"FAERS fetch failed for '{keyword}': {e}")
                        break
                if data is None:
                    break

                results = data.get("results", [])
                if not results:
                    break

                for report in results:
                    text = _build_synthetic_text(report, searched_drug=keyword)
                    report_id = report.get("safetyreportid", "")
                    received = _parse_faers_date(report.get("receivedate", ""))

                    all_posts.append(ScrapedPost(
                        source="faers",
                        keyword=keyword,
                        title=f"FDA FAERS Report #{report_id}",
                        text=text,
                        author="FDA FAERS",
                        url=f"https://www.fda.gov/safety/reporting-serious-problems-fda/safety-reporting-portal",
                        external_id=f"faers:{report_id}",
                        upvotes=0,
                        comment_count=0,
                        timestamp=received,
                    ))

                skip += batch_size
                meta = data.get("meta", {}).get("results", {})
                total_available = meta.get("total", 0)
                if skip >= min(total_available, limit):
                    break

                await asyncio.sleep(0.25)  # Respect rate limit: 240/min = ~4/sec

        logger.info(f"FAERS: fetched {len(all_posts)} reports for '{keyword}'")
        return self._deduplicate(all_posts)[:limit]
