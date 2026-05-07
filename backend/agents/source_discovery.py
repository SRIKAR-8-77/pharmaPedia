"""
Source Discovery Agent — finds new RSS/API data sources for a keyword.

Decision tree per DDG candidate URL:
  1. Domain already in global_sources → already_tracked
  2. Reddit URL → available (rss/api)
  3. RSS feed found via _probe_rss() → available
  4. API hints detected via _detect_api_hints() → available
  5. Gemini scores relevance ≥ 0.5 → suggestions (no free access found)
  6. Failed fetch / irrelevant → failed

Prototype constraint: returns at most ONE available source per call.
No DB writes — caller decides whether to persist.
"""
import json
import logging
import re
from urllib.parse import urlparse, quote_plus

import httpx
from duckduckgo_search import DDGS

from config import settings

logger = logging.getLogger(__name__)

# ── Redis DDG cache ───────────────────────────────────────────────────────────

_REDIS_CLIENT = None
_DDG_CACHE_TTL = 86400  # 24 hours


def _get_redis():
    global _REDIS_CLIENT
    if _REDIS_CLIENT is None:
        try:
            import redis
            _REDIS_CLIENT = redis.Redis(host="redis", port=6379, db=1, decode_responses=True)
            _REDIS_CLIENT.ping()
        except Exception:
            _REDIS_CLIENT = None
    return _REDIS_CLIENT


def _cache_key(query: str) -> str:
    return f"ddg:discovery:{query.lower().strip()}"


def _get_cached_urls(query: str) -> list[str] | None:
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(_cache_key(query))
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def _set_cached_urls(query: str, urls: list[str]) -> None:
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(_cache_key(query), _DDG_CACHE_TTL, json.dumps(urls))
    except Exception:
        pass


# ── Domain filters ────────────────────────────────────────────────────────────

_BLACKLISTED_DOMAINS = {
    "reuters.com", "bbc.com", "bbc.co.uk", "nytimes.com", "theguardian.com",
    "cnn.com", "apnews.com", "bloomberg.com", "wsj.com", "ft.com",
    "pfizer.com", "merck.com", "lilly.com", "novartis.com", "abbvie.com",
    "astrazeneca.com", "roche.com", "sanofi.com", "bms.com", "amgen.com",
    "wikipedia.org", "en.m.wikipedia.org",
    "mayoclinic.org", "healthline.com", "medicalnewstoday.com",
    "webmd.com", "drugs.com", "rxlist.com",
    "fda.gov", "nih.gov", "ema.europa.eu",  # handled by seeded global sources
}

_WHITELISTED_DOMAINS = {
    "patient.info", "healthunlocked.com", "inspire.com",
    "patientslikeme.com", "medhelp.org", "askapatient.com",
    "ehealthforums.com", "medschat.com",
}

_RSS_PROBE_PATHS = [
    "/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml",
    "/feed/rss", "/index.rss", "/feeds", "/blog/feed", "/forum/feed",
    "/rss/all", "/news/feed", "/posts.rss",
]

# ── Gemini assessment prompt ──────────────────────────────────────────────────

_ASSESSMENT_PROMPT = """You are a pharmacovigilance data engineer evaluating a website as a monitoring source.

Keyword: {keyword}
URL: {url}
Page title: {title}
Page excerpt (first 2000 chars):
{excerpt}

Assess this source. Respond with JSON ONLY (no markdown, no explanation):
{{
  "relevance_score": 0.0-1.0,
  "reason": "one sentence",
  "has_rss": true/false,
  "rss_url": "url or null",
  "is_reddit": true/false,
  "has_free_api": true/false,
  "api_base_url": "url or null",
  "supports_date_filtering": true/false,
  "fetch_url": "url or null"
}}

supports_date_filtering: true if the API accepts date/time query parameters (e.g. since=, from=, start_date=, dateFrom=, mindate=) so we can filter results by time range server-side.
fetch_url: the most direct URL to fetch data from (RSS endpoint, API endpoint, or page URL)."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_url(url: str) -> float | None:
    """Pre-filter: None = skip, 0-1 = priority score. No HTTP."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().lstrip("www.")
    for bad in _BLACKLISTED_DOMAINS:
        if netloc == bad or netloc.endswith("." + bad):
            return None
    for good in _WHITELISTED_DOMAINS:
        if netloc == good or netloc.endswith("." + good):
            return 1.0
    return 0.5


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip()[:200] if m else ""


def _is_reddit_url(url: str) -> bool:
    return "reddit.com" in urlparse(url).netloc


def _extract_subreddit(url: str) -> str | None:
    m = re.search(r"reddit\.com/r/([^/?#]+)", url)
    return m.group(1) if m else None


def _detect_api_hints(html: str, url: str) -> tuple[bool, str | None]:
    """Heuristic API detection from HTML content."""
    api_patterns = [
        r'href=["\']([^"\']*(?:/api/|/swagger|/openapi\.json|/api-docs)[^"\']*)["\']',
        r'href=["\']([^"\']*(?:developer\.)[^"\']*)["\']',
        r'"(https?://[^"\']+/api/v\d+[^"\']*)"',
    ]
    for pat in api_patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            found = m.group(1)
            if not found.startswith("http"):
                base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                found = base + found
            return True, found
    api_keywords = ["rest api", "api documentation", "developer api", "api key", "openapi", "swagger"]
    if any(kw in html.lower() for kw in api_keywords):
        return True, None
    return False, None


async def _probe_rss(base_url: str, html: str, http: httpx.AsyncClient) -> str | None:
    """Try to find a working RSS/Atom feed. Checks <head> link tags first, then 13 path patterns."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates: list[str] = []

    for m in re.finditer(
        r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    ):
        href = m.group(1)
        candidates.append(href if href.startswith("http") else origin + href)

    for m in re.finditer(
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\']',
        html, re.IGNORECASE
    ):
        href = m.group(1)
        url = href if href.startswith("http") else origin + href
        if url not in candidates:
            candidates.append(url)

    for suffix in _RSS_PROBE_PATHS:
        candidates.append(origin + suffix)

    for candidate in candidates:
        try:
            resp = await http.head(candidate, timeout=5)
            ct = resp.headers.get("content-type", "")
            if resp.status_code < 400 and ("xml" in ct or "rss" in ct or "atom" in ct):
                return candidate
        except Exception:
            continue
    return None


# ── Main discovery function ───────────────────────────────────────────────────

async def discover(keyword: str, existing_domains: set[str] | None = None) -> dict:
    """
    Discover new data sources for a keyword.

    existing_domains: set of domains already tracked in global_sources.
    Returns:
      {
        "already_tracked": [...],   # domain already in global_sources
        "available": [...],         # free RSS/API found — at most ONE (prototype limit)
        "suggestions": [...],       # relevant but no free access
        "failed": [...]             # fetch failed / irrelevant / blacklisted
      }
    """
    if existing_domains is None:
        existing_domains = set()

    already_tracked: list[dict] = []
    available: list[dict] = []
    suggestions: list[dict] = []
    failed: list[dict] = []

    # DDG search for candidate URLs
    queries = [
        f"{keyword} patient forum side effects",
        f"{keyword} adverse events community forum",
    ]
    candidate_urls: list[str] = []
    import asyncio as _asyncio
    try:
        with DDGS() as ddgs:
            for i, q in enumerate(queries):
                cached = _get_cached_urls(q)
                if cached is not None:
                    logger.info(f"DDG cache hit for '{q}' ({len(cached)} URLs)")
                    for href in cached:
                        if href not in candidate_urls:
                            candidate_urls.append(href)
                    continue

                if i > 0:
                    await _asyncio.sleep(3)
                try:
                    fresh: list[str] = []
                    for r in ddgs.text(q, max_results=6, backend="html"):
                        href = r.get("href", "")
                        if href:
                            fresh.append(href)
                            if href not in candidate_urls:
                                candidate_urls.append(href)
                    _set_cached_urls(q, fresh)
                except Exception as e:
                    err = str(e)
                    if "Ratelimit" in err or "202" in err or "Exception occurred" in err:
                        logger.info(f"DDG rate-limited — proceeding with {len(candidate_urls)} URLs")
                        break
                    logger.warning(f"DDG search error: {e}")
    except Exception as e:
        logger.info(f"DuckDuckGo unavailable ({type(e).__name__}) — no candidates found")

    # Pre-filter: blacklist + domain deduplication
    seen_domains: set[str] = set()
    filtered: list[tuple[str, float]] = []
    for url in candidate_urls:
        score = _score_url(url)
        if score is None:
            continue
        domain = urlparse(url).netloc.lower().lstrip("www.")
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        filtered.append((url, score))

    filtered.sort(key=lambda x: -x[1])
    candidate_urls = [u for u, _ in filtered[:8]]

    api_key = settings.GEMINI_API_KEY
    has_gemini = bool(api_key)

    async with httpx.AsyncClient(timeout=12, follow_redirects=True, verify=False) as http:
        for url in candidate_urls:
            domain = urlparse(url).netloc.lower().lstrip("www.")

            # Already in global_sources — no need to re-evaluate
            if domain in existing_domains:
                already_tracked.append({"url": url, "domain": domain, "reason": "Already tracked in global sources"})
                continue

            # Reddit shortcut
            if _is_reddit_url(url):
                sub = _extract_subreddit(url)
                if not available:
                    available.append({
                        "name": f"Reddit r/{sub or keyword}",
                        "url": url,
                        "domain": "reddit.com",
                        "category": "available",
                        "access_type": "rss",
                        "feed_url": f"https://www.reddit.com/r/{sub}/new/.rss" if sub else None,
                        "api_url": None,
                        "relevance_score": 0.80,
                        "reason": f"Reddit community — public RSS available",
                        "supports_date_range": True,
                    })
                continue

            # Fetch page HTML
            html = ""
            title = ""
            status_code = None
            fetch_error = None
            try:
                resp = await http.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; PharmaSignalBot/1.0)"})
                html = resp.text[:4000]
                title = _extract_title(html)
                status_code = resp.status_code
            except Exception as e:
                fetch_error = str(e)

            if fetch_error or not html:
                reason = fetch_error or "empty response"
                if status_code in (401, 403):
                    reason = "access denied (bot protection)"
                elif status_code == 429:
                    reason = "rate limited"
                failed.append({"url": url, "domain": domain, "reason": reason})
                continue

            # Prototype limit: stop evaluating after finding one available source
            if available:
                continue

            # Step 1: RSS probe
            rss_url = await _probe_rss(url, html, http)
            if rss_url:
                available.append({
                    "name": title or domain,
                    "url": url,
                    "domain": domain,
                    "category": "available",
                    "access_type": "rss",
                    "feed_url": rss_url,
                    "api_url": None,
                    "relevance_score": 0.70,
                    "reason": f"RSS feed found at {rss_url}",
                    "supports_date_range": False,
                })
                continue

            # Step 2: API hint detection
            has_api, api_url = _detect_api_hints(html, url)
            if has_api:
                available.append({
                    "name": title or domain,
                    "url": url,
                    "domain": domain,
                    "category": "available",
                    "access_type": "api",
                    "feed_url": None,
                    "api_url": api_url or url,
                    "relevance_score": 0.75,
                    "reason": "Free API or developer documentation detected",
                    "supports_date_range": False,
                })
                continue

            # Step 3: Gemini relevance check for suggestions
            relevance_score = 0.0
            reason = "No free RSS or API found"
            if has_gemini:
                try:
                    from google import genai as _genai
                    _client = _genai.Client(api_key=api_key)
                    _resp = await _client.aio.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=_ASSESSMENT_PROMPT.format(
                            keyword=keyword, url=url, title=title, excerpt=html[:2000]
                        ),
                    )
                    assessment = json.loads(re.sub(r"```(?:json)?", "", _resp.text).strip().strip("`"))
                    relevance_score = float(assessment.get("relevance_score", 0.0))
                    reason = assessment.get("reason", reason)

                    # Gemini found RSS or API we missed
                    if assessment.get("has_rss") and assessment.get("rss_url") and not available:
                        available.append({
                            "name": title or domain,
                            "url": url,
                            "domain": domain,
                            "category": "available",
                            "access_type": "rss",
                            "feed_url": assessment["rss_url"],
                            "fetch_url": assessment.get("fetch_url") or assessment["rss_url"],
                            "api_url": None,
                            "relevance_score": relevance_score,
                            "reason": reason,
                            "supports_date_range": bool(assessment.get("supports_date_filtering", False)),
                        })
                        continue
                    if assessment.get("has_free_api") and not available:
                        available.append({
                            "name": title or domain,
                            "url": url,
                            "domain": domain,
                            "category": "available",
                            "access_type": "api",
                            "feed_url": None,
                            "fetch_url": assessment.get("fetch_url") or assessment.get("api_base_url") or url,
                            "api_url": assessment.get("api_base_url") or url,
                            "relevance_score": relevance_score,
                            "reason": reason,
                            "supports_date_range": bool(assessment.get("supports_date_filtering", False)),
                        })
                        continue
                except Exception as e:
                    logger.debug(f"Gemini assessment failed for {url}: {e}")

            if relevance_score >= 0.5:
                suggestions.append({
                    "name": title or domain,
                    "url": url,
                    "domain": domain,
                    "category": "suggestion",
                    "access_type": None,
                    "feed_url": None,
                    "api_url": None,
                    "relevance_score": relevance_score,
                    "reason": f"Relevant site but no free RSS/API found. {reason}",
                    "supports_date_range": False,
                })
            else:
                failed.append({"url": url, "domain": domain, "reason": reason or "low relevance"})

    return {
        "already_tracked": already_tracked,
        "available": available,
        "suggestions": suggestions,
        "failed": failed,
    }
