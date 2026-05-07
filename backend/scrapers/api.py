"""
GenericAPIScraper — config-driven JSON API scraper.

All behaviour is read from scraper_config JSONB stored in global_sources.
Gemini auto-detects the field mapping once at source-add time via the
/global-sources/probe-api endpoint; users never fill this in manually.

Expected scraper_config keys:
  fetch_url      — URL template; supports {keyword}, {limit}, {since_iso}, {until_iso}
  api_key        — credential value (optional)
  auth_header    — header name to inject api_key into, e.g. "Authorization"
  auth_value     — header value template, e.g. "Bearer {api_key}" (optional, defaults to raw api_key)
  items_path     — dot-notation path to the results array, e.g. "data.results" (optional)
  title_field    — field name for post title (optional)
  text_field     — field name for post body/text
  author_field   — field name for author (optional)
  url_field      — field name for post URL (optional)
  id_field       — field name for unique ID (optional)
  date_field     — field name for timestamp (optional)
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote_plus

import httpx

from scrapers.base import BaseScraper, ScrapedPost

logger = logging.getLogger(__name__)

# Common field name fallbacks tried in order if configured field not found
_TEXT_FALLBACKS  = ["text", "body", "content", "summary", "description", "message", "abstract"]
_TITLE_FALLBACKS = ["title", "subject", "heading", "name"]
_DATE_FALLBACKS  = ["created_at", "published_at", "date", "timestamp", "pub_date", "created", "time"]
_URL_FALLBACKS   = ["url", "link", "href", "permalink"]
_ID_FALLBACKS    = ["id", "post_id", "uid", "guid", "external_id"]
_AUTHOR_FALLBACKS = ["author", "user", "username", "user_name", "by", "poster"]


def _get_nested(obj: dict, path: str):
    """Traverse dot-notation path in a nested dict. Returns None if missing."""
    for key in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _parse_date(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value[:26], fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
    return None


def _first_field(item: dict, candidates: list[str]) -> Optional[str]:
    for key in candidates:
        val = item.get(key)
        if val and isinstance(val, str):
            return val.strip()
    return None


class GenericAPIScraper(BaseScraper):
    source_type = "api"

    async def fetch(
        self,
        keyword: str,
        limit: int = 100,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[ScrapedPost]:
        cfg = self.config
        fetch_url = cfg.get("fetch_url") or cfg.get("feed_urls", [None])[0]
        if not fetch_url:
            logger.warning("GenericAPIScraper: no fetch_url in config")
            return []

        since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ") if since else ""
        until_iso = until.strftime("%Y-%m-%dT%H:%M:%SZ") if until else ""

        url = fetch_url.replace("{keyword}", quote_plus(keyword)) \
                       .replace("{limit}", str(limit)) \
                       .replace("{since_iso}", since_iso) \
                       .replace("{until_iso}", until_iso)

        # Build auth header
        headers: dict[str, str] = {"User-Agent": "PharmaPedia/1.0"}
        api_key = cfg.get("api_key", "")
        auth_header = cfg.get("auth_header", "")
        auth_value  = cfg.get("auth_value", "{api_key}")
        if api_key and auth_header:
            headers[auth_header] = auth_value.replace("{api_key}", api_key)
        elif api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning(f"GenericAPIScraper fetch error for {url}: {exc}")
            return []

        # Navigate to items array
        items_path = cfg.get("items_path", "")
        items = _get_nested(data, items_path) if items_path else data
        if isinstance(items, dict):
            # Try common wrapper keys
            for key in ("results", "items", "data", "posts", "articles", "entries", "records"):
                if isinstance(items.get(key), list):
                    items = items[key]
                    break
        if not isinstance(items, list):
            logger.warning(f"GenericAPIScraper: could not find items list in response from {url}")
            return []

        text_field   = cfg.get("text_field")
        title_field  = cfg.get("title_field")
        author_field = cfg.get("author_field")
        url_field    = cfg.get("url_field")
        id_field     = cfg.get("id_field")
        date_field   = cfg.get("date_field")

        posts: List[ScrapedPost] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue

            text = (item.get(text_field) if text_field else None) or _first_field(item, _TEXT_FALLBACKS)
            if not text:
                continue

            title  = (item.get(title_field)  if title_field  else None) or _first_field(item, _TITLE_FALLBACKS)
            author = (item.get(author_field) if author_field else None) or _first_field(item, _AUTHOR_FALLBACKS)
            post_url = (item.get(url_field)  if url_field    else None) or _first_field(item, _URL_FALLBACKS)
            ext_id   = (item.get(id_field)   if id_field     else None) or _first_field(item, _ID_FALLBACKS)

            raw_date = item.get(date_field) if date_field else None
            if not raw_date:
                for k in _DATE_FALLBACKS:
                    raw_date = item.get(k)
                    if raw_date:
                        break
            ts = _parse_date(raw_date) or datetime.now(tz=timezone.utc)

            if since and ts < since:
                continue
            if until and ts > until:
                continue

            posts.append(ScrapedPost(
                source="api",
                keyword=keyword,
                title=title,
                text=f"{title} {text}".strip() if title else text,
                author=author,
                url=post_url,
                external_id=str(ext_id) if ext_id else post_url,
                upvotes=item.get("upvotes") or item.get("likes") or item.get("score") or 0,
                comment_count=item.get("comments") or item.get("comment_count") or item.get("replies") or 0,
                timestamp=ts,
            ))

        return self._deduplicate(posts)
