import asyncio
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

import feedparser

from scrapers.base import BaseScraper, ScrapedPost

logger = logging.getLogger(__name__)


def _parse_timestamp(entry) -> datetime:
    """Extract a timezone-aware datetime from a feed entry."""
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return parsedate_to_datetime(val)
            except Exception:
                pass
    return datetime.now(timezone.utc)


class RSSFeedScraper(BaseScraper):
    source_type = "rss"

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
        feed_urls: List[str] = self.config.get("feed_urls", [])
        if not feed_urls:
            logger.warning("RSSFeedScraper: no feed_urls configured")
            return []

        posts: List[ScrapedPost] = []

        for url in feed_urls:
            try:
                feed = feedparser.parse(url)
                if feed.bozo and not feed.entries:
                    logger.warning(f"RSS parse error for {url}: {feed.bozo_exception}")
                    continue

                for entry in feed.entries[:limit]:
                    text = ""
                    if hasattr(entry, "summary"):
                        text = entry.summary
                    elif hasattr(entry, "content") and entry.content:
                        text = entry.content[0].get("value", "")

                    title = getattr(entry, "title", "")
                    combined = f"{title} {text}".strip()

                    if len(combined) < 20:
                        continue

                    ts = _parse_timestamp(entry)
                    # Client-side date filter (RSS has no server-side date params)
                    if since and ts < since:
                        continue
                    if until and ts > until:
                        continue

                    posts.append(ScrapedPost(
                        source="rss",
                        keyword=keyword,
                        title=title or None,
                        text=combined,
                        author=getattr(entry, "author", None),
                        url=getattr(entry, "link", None),
                        external_id=getattr(entry, "id", None) or getattr(entry, "link", None),
                        upvotes=0,
                        comment_count=0,
                        timestamp=ts,
                    ))

            except Exception as e:
                logger.error(f"RSS fetch failed for {url}: {e}")

        return self._deduplicate(posts)[:limit]
