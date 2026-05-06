-- Migration 004: Add supports_date_range flag to global_sources
-- Sources that support server-side date filtering participate in historical batch scrapes.
-- RSS feeds and newly-discovered sources default to FALSE (client-side filter only).

ALTER TABLE global_sources
    ADD COLUMN IF NOT EXISTS supports_date_range BOOLEAN NOT NULL DEFAULT FALSE;

-- FAERS, PubMed, Google News, Reddit all support since/until natively
UPDATE global_sources
    SET supports_date_range = TRUE
    WHERE source_type IN ('faers', 'pubmed', 'google_news', 'reddit');
