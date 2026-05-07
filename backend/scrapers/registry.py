"""
Scraper registry — maps source_type strings to scraper classes.

Two-tier architecture:
  Tier 1 — Official APIs      (FDA FAERS, PubMed): authoritative, free, no auth
  Tier 2 — RSS/No-auth feeds  (Google News, Reddit RSS, custom RSS): reliable, free
  Tier 3 — Social APIs        (Reddit PRAW, Twitter): rate-limited, credentials needed

All sources live in global_sources (shared) + project_global_sources (junction).
HTML scraping is not supported — use RSS or API sources only.
"""
from scrapers.base import BaseScraper
from scrapers.faers import FAERSScraper
from scrapers.pubmed import PubMedScraper
from scrapers.google_news import GoogleNewsScraper
from scrapers.rss import RSSFeedScraper
from scrapers.reddit import RedditScraper
from scrapers.twitter import TwitterScraper
from scrapers.api import GenericAPIScraper

SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    # ── Tier 1: Official APIs ─────────────────────────────────────────────────
    "faers":        FAERSScraper,        # FDA adverse event database
    "pubmed":       PubMedScraper,       # Peer-reviewed research abstracts

    # ── Tier 2: Free RSS / no-auth ────────────────────────────────────────────
    "google_news":  GoogleNewsScraper,   # Google News RSS (any keyword)
    "rss":          RSSFeedScraper,      # Generic RSS (custom feeds)
    "api":          GenericAPIScraper,   # Generic JSON API (config-driven, Gemini-probed)

    # ── Tier 3: Social APIs (credentials required) ────────────────────────────
    "reddit":       RedditScraper,       # PRAW API with RSS fallback
    "twitter":      TwitterScraper,      # twitterapi.io (limited credits)
}

# Tier metadata exposed to Admin UI and source discovery agent
SOURCE_TIERS: dict[str, dict] = {
    "faers":        {"tier": 1, "label": "Official API",    "color": "#22c55e", "auth_required": False},
    "pubmed":       {"tier": 1, "label": "Official API",    "color": "#22c55e", "auth_required": False},
    "google_news":  {"tier": 2, "label": "RSS Feed",        "color": "#3b82f6", "auth_required": False},
    "rss":          {"tier": 2, "label": "RSS Feed",        "color": "#3b82f6", "auth_required": False},
    "api":          {"tier": 2, "label": "JSON API",        "color": "#8b5cf6", "auth_required": False},
    "reddit":       {"tier": 3, "label": "Social API",      "color": "#f59e0b", "auth_required": True},
    "twitter":      {"tier": 3, "label": "Social API",      "color": "#f59e0b", "auth_required": True},
}


def get_scraper(source_type: str, config: dict) -> BaseScraper:
    cls = SCRAPER_REGISTRY.get(source_type)
    if not cls:
        raise ValueError(
            f"Unknown source type: '{source_type}'. "
            f"Registered types: {list(SCRAPER_REGISTRY)}"
        )
    return cls(config)


def register_scraper(source_type: str, cls: type[BaseScraper], tier: int = 4, label: str = "Custom"):
    """
    Dynamically register a new scraper at runtime.

    Used by the admin source discovery agent when it onboards a new website.
    For html_scraper instances with custom configs, site-specific source types
    can be registered here (e.g. "healthunlocked" → GenericHTMLScraper with preset config).
    """
    SCRAPER_REGISTRY[source_type] = cls
    if source_type not in SOURCE_TIERS:
        tier_colors = {1: "#22c55e", 2: "#3b82f6", 3: "#f59e0b", 4: "#a855f7"}
        SOURCE_TIERS[source_type] = {
            "tier": tier,
            "label": label,
            "color": tier_colors.get(tier, "#56617a"),
            "auth_required": False,
        }


def list_registered_scrapers() -> list[dict]:
    """Return all registered scraper types with tier metadata — used by Admin UI."""
    return [
        {
            "source_type": st,
            "class_name": cls.__name__,
            "description": getattr(cls, "source_description", ""),
            **SOURCE_TIERS.get(st, {"tier": 4, "label": "Custom", "color": "#56617a", "auth_required": False}),
        }
        for st, cls in SCRAPER_REGISTRY.items()
    ]


