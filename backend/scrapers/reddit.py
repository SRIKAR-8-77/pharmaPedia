"""
Reddit scraper — two-mode design:

Mode 1 (RSS, no auth):  Uses Reddit's public RSS endpoints — zero credentials needed,
                        works immediately. Tier 2 reliability.
Mode 2 (PRAW API):      Richer data (comments, upvotes) but requires credentials
                        and is rate-limited (~60 req/min). Falls back to RSS on auth error.

The scraper auto-detects which mode to use based on whether credentials are configured.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import quote_plus

import feedparser
from praw.exceptions import PRAWException

from config import settings
from scrapers.base import BaseScraper, ScrapedPost

logger = logging.getLogger(__name__)

# ── Shared PRAW state ──────────────────────────────────────────────────────────
# One Reddit instance per process — reuses the OAuth token and TCP connection
# instead of re-authenticating on every call.
_PRAW_CLIENT = None
_PRAW_SEMAPHORE = asyncio.Semaphore(3)  # max 3 concurrent subreddit fetches


def _get_praw_client():
    global _PRAW_CLIENT
    if _PRAW_CLIENT is None:
        import praw
        _PRAW_CLIENT = praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            user_agent=settings.REDDIT_USER_AGENT,
        )
    return _PRAW_CLIENT

# Drug → relevant subreddits mapping (used by both modes)
DEFAULT_SUBREDDITS = {
    "ozempic":    ["Ozempic", "GLP1_Medications", "WeightLossAdvice", "diabetes", "diabetes_t2"],
    "semaglutide":["Ozempic", "GLP1_Medications", "diabetes"],
    "wegovy":     ["Ozempic", "GLP1_Medications", "WeightLossAdvice"],
    "metformin":  ["diabetes", "diabetes_t2", "MetabolicHealth", "PCOS"],
    "mounjaro":   ["mounjaro", "GLP1_Medications", "diabetes_t2"],
    "tirzepatide":["mounjaro", "GLP1_Medications", "diabetes"],
    "default":    ["AskDocs", "medical", "pharmacy", "health"],
}


def _has_credentials() -> bool:
    return bool(
        settings.REDDIT_CLIENT_ID
        and settings.REDDIT_CLIENT_ID != "your_reddit_client_id"
        and settings.REDDIT_CLIENT_SECRET
        and settings.REDDIT_CLIENT_SECRET != "your_reddit_client_secret"
    )


def _resolve_subreddits(keyword: str, custom: List[str]) -> List[str]:
    if custom:
        return custom
    key = keyword.lower()
    for k, subs in DEFAULT_SUBREDDITS.items():
        if k in key:
            return subs
    return DEFAULT_SUBREDDITS["default"]


def _parse_rss_date(entry) -> datetime:
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return parsedate_to_datetime(val)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


# ── Mode 1: No-auth RSS ────────────────────────────────────────────────────────

def _fetch_via_rss(
    keyword: str,
    subreddits: List[str],
    limit: int,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> List[ScrapedPost]:
    """Fetch posts using Reddit's public RSS endpoints — no credentials needed."""
    posts: List[ScrapedPost] = []
    encoded_kw = quote_plus(keyword)

    urls = [f"https://www.reddit.com/r/{sub}/new/.rss?limit=25" for sub in subreddits[:4]]
    urls.append(f"https://www.reddit.com/search.rss?q={encoded_kw}+site:reddit.com&sort=new&t=month&limit=25")

    per_url = max(5, limit // len(urls))

    for url in urls:
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                logger.debug(f"Reddit RSS parse issue: {url}")
                continue

            for entry in feed.entries[:per_url]:
                title = getattr(entry, "title", "")
                summary = _strip_html(getattr(entry, "summary", ""))
                text = f"{title}. {summary}".strip(" .")

                if len(text) < 25:
                    continue

                kw_lower = keyword.lower()
                if kw_lower not in text.lower() and kw_lower not in url:
                    continue

                ts = _parse_rss_date(entry)
                if since and ts < since:
                    continue
                if until and ts > until:
                    continue

                posts.append(ScrapedPost(
                    source="reddit",
                    keyword=keyword,
                    title=title or None,
                    text=text,
                    author=getattr(entry, "author", None),
                    url=getattr(entry, "link", None),
                    external_id=getattr(entry, "id", None) or getattr(entry, "link", None),
                    upvotes=0,
                    comment_count=0,
                    timestamp=ts,
                ))

        except Exception as e:
            logger.error(f"Reddit RSS fetch failed {url}: {e}")

    return posts


# ── Mode 2: PRAW API ───────────────────────────────────────────────────────────

def _since_to_time_filter(since: Optional[datetime]) -> str:
    """Map a since datetime to the closest PRAW time_filter string."""
    if since is None:
        return "month"
    age = datetime.now(timezone.utc) - since
    if age <= timedelta(hours=1):
        return "hour"
    if age <= timedelta(days=1):
        return "day"
    if age <= timedelta(weeks=1):
        return "week"
    if age <= timedelta(days=31):
        return "month"
    if age <= timedelta(days=365):
        return "year"
    return "all"


def _fetch_via_praw(
    keyword: str,
    subreddits: List[str],
    limit: int,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> List[ScrapedPost]:
    """
    Fetch via PRAW Reddit API. Richer data but rate-limited and requires credentials.
    Reuses the module-level singleton client. Falls back to RSS on auth failure.
    Note: Reddit search has unreliable historical access beyond ~2 months.
    """
    try:
        client = _get_praw_client()
        client.user.me()
    except Exception as e:
        logger.warning(f"PRAW auth failed ({e}), falling back to RSS mode")
        global _PRAW_CLIENT
        _PRAW_CLIENT = None
        return _fetch_via_rss(keyword, subreddits, limit, since, until)

    if since and (datetime.now(timezone.utc) - since) > timedelta(days=60):
        logger.warning(f"Reddit PRAW: requested since={since.date()} is >60 days ago — Reddit's search is unreliable for historical data this old")

    time_filter = _since_to_time_filter(since)
    posts: List[ScrapedPost] = []
    per_sub = max(5, limit // len(subreddits))

    for sub_name in subreddits:
        try:
            sub = client.subreddit(sub_name)
            for submission in sub.search(keyword, limit=per_sub, sort="new", time_filter=time_filter):
                ts = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
                if since and ts < since:
                    continue
                if until and ts > until:
                    continue
                text = submission.selftext.strip() or submission.title
                if len(text) < 20:
                    continue
                posts.append(ScrapedPost(
                    source="reddit",
                    keyword=keyword,
                    title=submission.title,
                    text=text,
                    author=str(submission.author) if submission.author else "[deleted]",
                    url=f"https://reddit.com{submission.permalink}",
                    external_id=submission.id,
                    upvotes=submission.score,
                    comment_count=submission.num_comments,
                    timestamp=ts,
                ))
                try:
                    submission.comments.replace_more(limit=0)
                    for comment in submission.comments[:5]:
                        if hasattr(comment, "body") and len(comment.body) > 30:
                            cts = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc)
                            if since and cts < since:
                                continue
                            posts.append(ScrapedPost(
                                source="reddit",
                                keyword=keyword,
                                title=None,
                                text=comment.body,
                                author=str(comment.author) if comment.author else "[deleted]",
                                url=f"https://reddit.com{comment.permalink}",
                                external_id=comment.id,
                                upvotes=comment.score,
                                comment_count=0,
                                timestamp=cts,
                            ))
                except Exception:
                    pass
            import time; time.sleep(0.5)
        except PRAWException as e:
            logger.warning(f"PRAW error r/{sub_name} keyword={keyword}: {e}")
        except Exception as e:
            logger.error(f"Unexpected PRAW error r/{sub_name}: {e}")

    return posts


# ── Scraper class ──────────────────────────────────────────────────────────────

class RedditScraper(BaseScraper):
    """
    Reddit scraper with automatic fallback:
    - If credentials are configured → PRAW (richer data, rate-limited)
    - If no credentials → RSS (no auth, always works, sufficient for demo)
    """
    source_type = "reddit"
    reliability_tier = 3
    source_description = "Reddit (PRAW API with RSS fallback when no credentials)"

    async def fetch(
        self,
        keyword: str,
        limit: int = 100,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[ScrapedPost]:
        async with _PRAW_SEMAPHORE:
            return await asyncio.to_thread(self._fetch_sync, keyword, limit, since, until)

    def _fetch_sync(
        self,
        keyword: str,
        limit: int,
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> List[ScrapedPost]:
        custom_subs: List[str] = self.config.get("subreddits", [])
        subreddits = _resolve_subreddits(keyword, custom_subs)

        if _has_credentials():
            logger.info(f"Reddit: using PRAW for '{keyword}'")
            posts = _fetch_via_praw(keyword, subreddits, limit, since, until)
        else:
            logger.info(f"Reddit: using RSS fallback (no credentials) for '{keyword}'")
            posts = _fetch_via_rss(keyword, subreddits, limit, since, until)

        return self._deduplicate(posts)[:limit]
