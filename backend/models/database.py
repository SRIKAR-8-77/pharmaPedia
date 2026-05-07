from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import (
    Column, String, Integer, Boolean, Float, Text, DateTime, JSON,
    ForeignKey, Enum as SAEnum, func, Index
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
import uuid
import enum
from datetime import datetime

from config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ─── Enums ────────────────────────────────────────────────────────────────────

class SourceLatency(str, enum.Enum):
    realtime = "realtime"
    daily = "daily"
    weekly = "weekly"


class SourceStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    healing = "healing"
    error = "error"


class SignalSeverity(str, enum.Enum):
    HIGH = "HIGH"
    MED = "MED"
    LOW = "LOW"


class TriageAction(str, enum.Enum):
    escalate = "escalate"
    monitor = "monitor"
    dismiss = "dismiss"
    pending = "pending"


class PIIReviewAction(str, enum.Enum):
    approve_redacted = "approve_redacted"
    delete = "delete"
    false_positive = "false_positive"
    pending = "pending"


# ─── Tables ───────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    keywords = Column(ARRAY(Text), nullable=False, default=[])
    sources = Column(ARRAY(Text), nullable=False, default=[])
    alert_rules = Column(JSONB, nullable=False, default={})
    is_active = Column(Boolean, default=True)
    is_paused = Column(Boolean, default=False)
    date_from = Column(DateTime(timezone=True), nullable=True)   # start of monitoring window
    date_to   = Column(DateTime(timezone=True), nullable=True)   # end of window; null = live/ongoing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SourceConfig(Base):
    __tablename__ = "source_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(50), nullable=False)   # reddit, twitter, rss, forum
    name = Column(String(255), nullable=False)
    url = Column(Text, nullable=True)
    selectors = Column(JSONB, nullable=False, default={})   # CSS/XPath selectors for scrapers
    scraper_config = Column(JSONB, nullable=False, default={})  # full YAML config stored as JSON
    latency = Column(SAEnum(SourceLatency), nullable=False, default=SourceLatency.daily)
    status = Column(SAEnum(SourceStatus), nullable=False, default=SourceStatus.active)
    enabled = Column(Boolean, default=True)
    last_run = Column(DateTime(timezone=True), nullable=True)
    posts_per_hour = Column(Float, default=0.0)
    error_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_source_configs_project_id", "project_id"),
    )


class RawPost(Base):
    __tablename__ = "raw_posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(50), nullable=False)        # reddit, twitter, rss, forum
    source_config_id = Column(UUID(as_uuid=True), ForeignKey("source_configs.id", ondelete="SET NULL"), nullable=True)
    keyword = Column(String(255), nullable=False)
    text = Column(Text, nullable=False)
    title = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    url = Column(Text, nullable=True)
    external_id = Column(String(255), nullable=True)   # reddit post id, tweet id, etc.
    upvotes = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_raw_posts_project_id", "project_id"),
        Index("ix_raw_posts_processed", "processed"),
        Index("ix_raw_posts_timestamp", "timestamp"),
        Index("ix_raw_posts_source", "source"),
    )


class EnrichedPost(Base):
    __tablename__ = "enriched_posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_post_id = Column(UUID(as_uuid=True), ForeignKey("raw_posts.id", ondelete="CASCADE"), nullable=False, unique=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # Step 1 — cleaned text
    clean_text = Column(Text, nullable=False)
    language = Column(String(10), default="en")

    # Step 2 — PII
    has_pii = Column(Boolean, default=False)
    pii_types = Column(ARRAY(Text), default=[])

    # Step 3 — entities
    drugs = Column(ARRAY(Text), default=[])
    symptoms = Column(ARRAY(Text), default=[])
    conditions = Column(ARRAY(Text), default=[])
    dosages = Column(ARRAY(Text), default=[])
    negated_entities = Column(JSONB, default={})    # {drugs:[], symptoms:[]}

    # Step 4 — sentiment
    sentiment = Column(String(20), nullable=True)   # positive / neutral / negative
    sentiment_score = Column(Float, nullable=True)  # -1.0 to 1.0
    entity_sentiment = Column(JSONB, default={})    # {drug: score, symptom: score}

    # Step 5 — safety signals
    has_safety_signal = Column(Boolean, default=False)
    safety_severity = Column(SAEnum(SignalSeverity), nullable=True)
    safety_signals = Column(JSONB, default=[])       # [{drug, symptom, severity, context, causality}]
    causality = Column(String(50), nullable=True)    # definite / probable / possible / unlikely

    # Step 5b — MedDRA
    meddra_terms = Column(JSONB, default=[])         # [{term, code, llt_code}]

    # Step 6 — relevance
    relevance_score = Column(Float, default=0.0)
    is_duplicate = Column(Boolean, default=False)
    minhash_signature = Column(JSONB, nullable=True)

    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_enriched_posts_project_id", "project_id"),
        Index("ix_enriched_posts_has_safety_signal", "has_safety_signal"),
        Index("ix_enriched_posts_safety_severity", "safety_severity"),
    )


class SafetySignal(Base):
    __tablename__ = "safety_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enriched_post_id = Column(UUID(as_uuid=True), ForeignKey("enriched_posts.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    drug = Column(String(255), nullable=False)
    symptom = Column(String(255), nullable=False)
    severity = Column(SAEnum(SignalSeverity), nullable=False)
    meddra_term = Column(String(255), nullable=True)
    meddra_code = Column(String(50), nullable=True)
    causality = Column(String(50), nullable=True)
    confidence = Column(Float, default=0.0)
    context_window = Column(Text, nullable=True)    # 50-char snippet around signal
    triage_action = Column(SAEnum(TriageAction), default=TriageAction.pending)
    triage_rationale = Column(Text, nullable=True)
    triage_ai_result = Column(JSONB, nullable=True)
    triaged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_safety_signals_project_id", "project_id"),
        Index("ix_safety_signals_drug", "drug"),
        Index("ix_safety_signals_severity", "severity"),
    )


class CanvasState(Base):
    __tablename__ = "canvas_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    cards = Column(JSONB, nullable=False, default=[])   # [{id, type, title, position, size, data, pinned}]
    share_id = Column(String(64), nullable=True, unique=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PIIQueue(Base):
    __tablename__ = "pii_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_post_id = Column(UUID(as_uuid=True), ForeignKey("raw_posts.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    pii_types = Column(ARRAY(Text), default=[])
    original_text = Column(Text, nullable=False)
    redacted_text = Column(Text, nullable=True)
    pii_spans = Column(JSONB, default=[])            # [{start, end, type, text}]
    reviewer_action = Column(SAEnum(PIIReviewAction), default=PIIReviewAction.pending)
    reviewed_by = Column(String(255), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_pii_queue_project_id", "project_id"),
        Index("ix_pii_queue_reviewer_action", "reviewer_action"),
    )


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    content = Column(JSONB, nullable=False, default={})   # {executive_summary, notable_signals, recommended_actions}
    pdf_path = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_reports_project_id", "project_id"),
    )


class GlobalSource(Base):
    """
    Permanent, shared RSS/API sources. Grows over time — every new project
    gets these for free without re-running discovery.
    Only tier 1-2 sources live here (faers, pubmed, rss, reddit, google_news).
    HTML scrapers are never added here — they go in source_configs scoped to a project.
    """
    __tablename__ = "global_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)   # faers, pubmed, rss, reddit, google_news
    url = Column(Text, nullable=False)
    feed_url = Column(Text, nullable=True)             # supports {keyword} placeholder
    scraper_config = Column(JSONB, nullable=False, default={})
    reliability_tier = Column(Integer, default=2)      # 1=official API, 2=RSS/no-auth
    supports_date_range = Column(Boolean, default=False)  # True = server-side since/until filtering
    total_posts_pulled = Column(Integer, default=0)
    last_successful_run = Column(DateTime(timezone=True), nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)


class ProjectGlobalSource(Base):
    """Junction table: which projects use which global sources, per keyword."""
    __tablename__ = "project_global_sources"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    global_source_id = Column(UUID(as_uuid=True), ForeignKey("global_sources.id", ondelete="CASCADE"), primary_key=True)
    keyword = Column(String(255), nullable=False, primary_key=True)
    enabled = Column(Boolean, default=True)
    latency = Column(SAEnum(SourceLatency), nullable=False, default=SourceLatency.daily)

    __table_args__ = (
        Index("ix_project_global_sources_project_id", "project_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=True)
    action = Column(String(255), nullable=False)    # triage_signal, pii_review, export, copilot_call, etc.
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(255), nullable=True)
    query_params = Column(JSONB, nullable=True)
    result_count = Column(Integer, nullable=True)
    model_version = Column(String(100), nullable=True)
    confidence_range = Column(JSONB, nullable=True)   # {min, max}
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_timestamp", "timestamp"),
    )


# ─── Dependency ───────────────────────────────────────────────────────────────

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    import asyncio
    from sqlalchemy import text
    for attempt in range(10):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            break
        except Exception as e:
            if attempt < 9:
                wait = min(2 ** attempt, 30)
                print(f"DB not ready (attempt {attempt + 1}/10), retrying in {wait}s: {e}")
                await asyncio.sleep(wait)
            else:
                raise

    # Seed baseline global sources — idempotent (ON CONFLICT DO NOTHING)
    seed_sql = text("""
        INSERT INTO global_sources
            (domain, name, source_type, url, feed_url, scraper_config,
             reliability_tier, is_active, supports_date_range)
        VALUES
          ('api.fda.gov', 'FDA FAERS API', 'faers',
           'https://api.fda.gov/drug/event.json', NULL, '{}', 1, TRUE, TRUE),
          ('pubmed.ncbi.nlm.nih.gov', 'PubMed E-Utilities', 'pubmed',
           'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/', NULL, '{}', 1, TRUE, TRUE),
          ('news.google.com', 'Google News RSS', 'google_news',
           'https://news.google.com/rss/search',
           'https://news.google.com/rss/search?q={keyword}+adverse+effects&hl=en-US',
           '{}', 2, TRUE, TRUE),
          ('reddit.com', 'Reddit', 'reddit',
           'https://www.reddit.com',
           'https://www.reddit.com/search.rss?q={keyword}+side+effects&sort=new',
           '{}', 2, TRUE, TRUE)
        ON CONFLICT (domain) DO NOTHING
    """)
    async with AsyncSessionLocal() as session:
        await session.execute(seed_sql)
        await session.commit()
    print("DB initialised and sources seeded.")
