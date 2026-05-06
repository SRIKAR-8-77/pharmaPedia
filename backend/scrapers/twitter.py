"""
Twitter/X scraper using twitterapi.io.
Phase 1: stub that returns pre-seeded data from the database.
Phase 5: replace with live twitterapi.io calls.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from config import settings
from scrapers.base import BaseScraper, ScrapedPost

logger = logging.getLogger(__name__)

TWITTERAPI_BASE = "https://api.twitterapi.io/twitter/tweet/advanced_search"

_TWITTER_KEY_INVALID = False  # Set to True after first 401 so we don't spam per-keyword


class TwitterScraper(BaseScraper):
    source_type = "twitter"

    async def fetch(
        self,
        keyword: str,
        limit: int = 100,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[ScrapedPost]:
        global _TWITTER_KEY_INVALID

        key = settings.TWITTER_API_KEY
        if not key or key.startswith("your_") or _TWITTER_KEY_INVALID:
            logger.debug("Twitter API key not configured — skipping Twitter source")
            return []

        params: dict = {
            "query": f"{keyword} lang:en -is:retweet",
            "queryType": "Latest",
            "count": min(limit, 100),
        }
        # twitterapi.io accepts ISO 8601 date filters (free tier: last 7 days only)
        if since:
            params["startTime"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        if until:
            params["endTime"] = until.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    TWITTERAPI_BASE,
                    headers={"X-API-Key": key},
                    params=params,
                )
                if resp.status_code == 401:
                    _TWITTER_KEY_INVALID = True
                    logger.warning("Twitter API key is invalid (401) — Twitter source disabled until restart")
                    return []
                resp.raise_for_status()
                data = resp.json()

        except httpx.HTTPStatusError:
            return []
        except Exception as e:
            logger.error(f"Twitter fetch failed for keyword={keyword}: {e}")
            return []

        posts = []
        for tweet in data.get("tweets", []):
            text = tweet.get("text", "")
            if len(text) < 20:
                continue
            posts.append(ScrapedPost(
                source="twitter",
                keyword=keyword,
                text=text,
                author=tweet.get("author", {}).get("userName"),
                url=f"https://twitter.com/i/web/status/{tweet.get('id')}",
                external_id=tweet.get("id"),
                upvotes=tweet.get("likeCount", 0),
                comment_count=tweet.get("replyCount", 0),
                timestamp=datetime.now(timezone.utc),
            ))
        return self._deduplicate(posts)
