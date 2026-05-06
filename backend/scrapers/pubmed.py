"""
PubMed / NCBI E-utilities scraper.

Uses the NCBI E-utilities API — completely free, no authentication required.
Returns peer-reviewed research abstracts mentioning drug adverse effects.

Tier 1: Official scientific literature — adds clinical credibility to the signal layer.

API docs: https://www.ncbi.nlm.nih.gov/books/NBK25500/
Rate limit: 3 req/sec unauthenticated, 10/sec with NCBI API key (optional).
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import httpx

from scrapers.base import BaseScraper, ScrapedPost

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

PHARMA_MESH_TERMS = [
    "adverse effects[MeSH Subheading]",
    "drug-related side effects and adverse reactions[MeSH Terms]",
]


class PubMedScraper(BaseScraper):
    """
    Fetches PubMed research abstracts relevant to drug adverse effects.
    Tier 1 source: peer-reviewed literature, highest signal credibility.
    """
    source_type = "pubmed"
    reliability_tier = 1
    source_description = "PubMed NCBI E-utilities (free API, peer-reviewed research abstracts)"

    async def fetch(
        self,
        keyword: str,
        limit: int = 50,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[ScrapedPost]:
        api_key = self.config.get("ncbi_api_key", "")
        # Date window — fall back to lookback_days config when not specified
        end_dt = until or datetime.now(timezone.utc)
        if since:
            start_dt = since
        else:
            lookback_days = self.config.get("lookback_days", 365)
            start_dt = end_dt - timedelta(days=lookback_days)

        async with httpx.AsyncClient(timeout=20) as client:
            pmids = await self._search_pmids(client, keyword, limit, api_key, start_dt, end_dt)
            if not pmids:
                logger.info(f"PubMed: no results for '{keyword}'")
                return []

            await asyncio.sleep(0.35)  # 3 req/sec limit
            posts = await self._fetch_abstracts(client, pmids, keyword, api_key)

        logger.info(f"PubMed: fetched {len(posts)} abstracts for '{keyword}'")
        return posts

    async def _search_pmids(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        limit: int,
        api_key: str,
        since: datetime,
        until: datetime,
    ) -> List[str]:
        query = f'("{keyword}"[Title/Abstract]) AND (adverse effects OR side effects OR toxicity)'
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": min(limit, 50),
            "retmode": "json",
            "sort": "date",
            "datetype": "pdat",
            "mindate": since.strftime("%Y/%m/%d"),
            "maxdate": until.strftime("%Y/%m/%d"),
        }
        if api_key:
            params["api_key"] = api_key

        try:
            resp = await client.get(ESEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("esearchresult", {}).get("idlist", [])
        except Exception as e:
            logger.error(f"PubMed esearch failed for '{keyword}': {e}")
            return []

    async def _fetch_abstracts(
        self, client: httpx.AsyncClient, pmids: List[str], keyword: str, api_key: str
    ) -> List[ScrapedPost]:
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        if api_key:
            params["api_key"] = api_key

        try:
            resp = await client.get(EFETCH_URL, params=params)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"PubMed efetch failed: {e}")
            return []

        posts = []
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            logger.error(f"PubMed XML parse error: {e}")
            return []

        for article in root.findall(".//PubmedArticle"):
            try:
                pmid_el = article.find(".//PMID")
                pmid = pmid_el.text if pmid_el is not None else "unknown"

                # Title
                title_el = article.find(".//ArticleTitle")
                title = "".join(title_el.itertext()) if title_el is not None else ""

                # Abstract text (may have multiple sections)
                abstract_parts = []
                for ab in article.findall(".//AbstractText"):
                    label = ab.get("Label", "")
                    text_part = "".join(ab.itertext())
                    if label:
                        abstract_parts.append(f"{label}: {text_part}")
                    else:
                        abstract_parts.append(text_part)
                abstract = " ".join(abstract_parts)

                if not abstract and not title:
                    continue

                # Authors
                authors = []
                for author in article.findall(".//Author")[:3]:
                    last = author.findtext("LastName", "")
                    fore = author.findtext("ForeName", "")
                    if last:
                        authors.append(f"{fore} {last}".strip())
                author_str = ", ".join(authors) + (" et al." if len(authors) == 3 else "") if authors else "Unknown"

                # Journal + year
                journal = article.findtext(".//Journal/Title", "") or article.findtext(".//ISOAbbreviation", "")
                year = article.findtext(".//PubDate/Year", "")
                month = article.findtext(".//PubDate/Month", "")

                # Publication date
                pub_date = datetime.now(timezone.utc)
                if year:
                    try:
                        month_num = {
                            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
                        }.get(month, 1) if month and not month.isdigit() else int(month or 1)
                        pub_date = datetime(int(year), month_num, 1, tzinfo=timezone.utc)
                    except ValueError:
                        pass

                # Compose text for NLP — title + abstract gives rich signal context
                full_text = f"{title}. {abstract}".strip(" .")
                if len(full_text) < 30:
                    continue

                posts.append(ScrapedPost(
                    source="pubmed",
                    keyword=keyword,
                    title=title or None,
                    text=full_text,
                    author=author_str,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    external_id=f"pmid:{pmid}",
                    upvotes=0,
                    comment_count=0,
                    timestamp=pub_date,
                ))
            except Exception as e:
                logger.warning(f"PubMed article parse error (pmid loop): {e}")

        return posts
