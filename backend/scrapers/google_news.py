"""
Google News RSS scraper.

Uses Google News RSS feeds — completely free, no API key, no authentication.
Tier 2: reliable, keyword-based, covers mainstream news and major health publications.

Feed format: https://news.google.com/rss/search?q={keyword}&hl=en-US&gl=US&ceid=US:en
"""
import asyncio
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import quote_plus

import feedparser

from scrapers.base import BaseScraper, ScrapedPost

logger = logging.getLogger(__name__)


def _build_google_news_urls(keyword: str, since: Optional[datetime] = None) -> List[str]:
    """Generate Google News RSS URLs. Appends after:YYYY-MM-DD when since is provided."""
    encoded_kw = quote_plus(keyword)
    date_suffix = f"+after:{since.strftime('%Y-%m-%d')}" if since else ""
    return [
        f"https://news.google.com/rss/search?q={encoded_kw}+adverse+effects{date_suffix}&hl=en-US&gl=US&ceid=US:en",
        f"https://news.google.com/rss/search?q={encoded_kw}+side+effects{date_suffix}&hl=en-US&gl=US&ceid=US:en",
        f"https://news.google.com/rss/search?q={encoded_kw}+FDA+warning{date_suffix}&hl=en-US&gl=US&ceid=US:en",
    ]


def _parse_feed_date(entry) -> datetime:
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return parsedate_to_datetime(val)
            except Exception:
                pass
    return datetime.now(timezone.utc)


class GoogleNewsScraper(BaseScraper):
    """
    Fetches drug-related news articles from Google News RSS.
    No API key required. Covers mainstream health journalism and FDA press releases.
    Tier 2 source: reliable, good signal-to-noise for safety news.
    """
    source_type = "google_news"
    reliability_tier = 2
    source_description = "Google News RSS (free, no auth, mainstream media coverage)"

    async def fetch(
        self,
        keyword: str,
        limit: int = 100,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[ScrapedPost]:
        return await asyncio.to_thread(self._fetch_sync, keyword, limit, since, until)

    def _fetch_sync(
        self,
        keyword: str,
        limit: int,
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> List[ScrapedPost]:
        configured_urls: List[str] = self.config.get("feed_urls", [])
        auto_urls = _build_google_news_urls(keyword, since=since)
        all_urls = list(dict.fromkeys(configured_urls + auto_urls))

        posts: List[ScrapedPost] = []
        per_feed = max(1, limit // len(all_urls))

        for url in all_urls:
            try:
                feed = feedparser.parse(url)
                if feed.bozo and not feed.entries:
                    logger.debug(f"Google News RSS parse issue for {url}")
                    continue

                for entry in feed.entries[:per_feed]:
                    title = getattr(entry, "title", "")
                    summary = getattr(entry, "summary", "")
                    # Google News summaries sometimes contain HTML — strip basic tags
                    import re
                    summary = re.sub(r"<[^>]+>", " ", summary).strip()
                    text = f"{title}. {summary}".strip(" .")

                    if len(text) < 20:
                        continue

                    source_name = getattr(entry, "source", {})
                    if hasattr(source_name, "title"):
                        source_name = source_name.title
                    elif isinstance(source_name, dict):
                        source_name = source_name.get("title", "Google News")
                    else:
                        source_name = "Google News"

                    posts.append(ScrapedPost(
                        source="google_news",
                        keyword=keyword,
                        title=title or None,
                        text=text,
                        author=source_name,
                        url=getattr(entry, "link", None),
                        external_id=getattr(entry, "id", None) or getattr(entry, "link", None),
                        upvotes=0,
                        comment_count=0,
                        timestamp=_parse_feed_date(entry),
                    ))

            except Exception as e:
                logger.error(f"Google News RSS failed for {url}: {e}")

        return self._deduplicate(posts)[:limit]
