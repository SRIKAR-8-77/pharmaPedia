-- Two-tier source registry: global sources (shared) + project junction table

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS global_sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    url TEXT NOT NULL,
    feed_url TEXT,
    scraper_config JSONB DEFAULT '{}',
    reliability_tier INTEGER DEFAULT 2,
    total_posts_pulled INTEGER DEFAULT 0,
    last_successful_run TIMESTAMP WITH TIME ZONE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS project_global_sources (
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    global_source_id UUID REFERENCES global_sources(id) ON DELETE CASCADE,
    keyword VARCHAR(255) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    latency sourcelatency DEFAULT 'daily',
    PRIMARY KEY (project_id, global_source_id, keyword)
);

CREATE INDEX IF NOT EXISTS ix_project_global_sources_project_id
    ON project_global_sources (project_id);

-- Seed the 4 guaranteed baseline sources
INSERT INTO global_sources (id, domain, name, source_type, url, feed_url, scraper_config, reliability_tier) VALUES
  (uuid_generate_v4(), 'api.fda.gov', 'FDA FAERS API', 'faers',
   'https://api.fda.gov/drug/event.json', NULL, '{}', 1),
  (uuid_generate_v4(), 'pubmed.ncbi.nlm.nih.gov', 'PubMed E-Utilities', 'pubmed',
   'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/', NULL, '{}', 1),
  (uuid_generate_v4(), 'news.google.com', 'Google News RSS', 'google_news',
   'https://news.google.com/rss/search',
   'https://news.google.com/rss/search?q={keyword}+adverse+effects&hl=en-US', '{}', 2),
  (uuid_generate_v4(), 'reddit.com', 'Reddit', 'reddit',
   'https://www.reddit.com',
   'https://www.reddit.com/search.rss?q={keyword}+side+effects&sort=new', '{}', 2)
ON CONFLICT (domain) DO NOTHING;
