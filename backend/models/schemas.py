from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from models.database import SourceLatency, SourceStatus, SignalSeverity, TriageAction, PIIReviewAction


# ─── Project ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    keywords: List[str] = Field(..., min_length=1)
    selected_source_ids: Optional[List[UUID]] = None  # UUIDs from global_sources; null = link all
    alert_rules: Dict[str, Any] = Field(default={})
    date_from: Optional[datetime] = None   # start of monitoring window
    date_to: Optional[datetime] = None     # end of window; null = live/ongoing

    @field_validator("keywords")
    @classmethod
    def keywords_not_empty(cls, v):
        cleaned = [k.strip().lower() for k in v if k.strip()]
        if not cleaned:
            raise ValueError("At least one keyword is required")
        return cleaned


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    sources: Optional[List[str]] = None
    alert_rules: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_paused: Optional[bool] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    keywords: List[str]
    sources: List[str]
    alert_rules: Dict[str, Any]
    is_active: bool
    is_paused: bool = False
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    post_count: int = 0
    signal_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Source Config ────────────────────────────────────────────────────────────

class SourceConfigCreate(BaseModel):
    project_id: UUID
    source_type: str
    name: str
    url: Optional[str] = None
    selectors: Dict[str, Any] = {}
    scraper_config: Dict[str, Any] = {}
    latency: SourceLatency = SourceLatency.daily
    enabled: bool = True


class SourceConfigUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    selectors: Optional[Dict[str, Any]] = None
    scraper_config: Optional[Dict[str, Any]] = None
    latency: Optional[SourceLatency] = None
    status: Optional[SourceStatus] = None
    enabled: Optional[bool] = None


class SourceConfigResponse(BaseModel):
    id: UUID
    project_id: UUID
    source_type: str
    name: str
    url: Optional[str]
    selectors: Dict[str, Any]
    scraper_config: Dict[str, Any]
    latency: SourceLatency
    status: SourceStatus
    enabled: bool
    last_run: Optional[datetime]
    posts_per_hour: float
    error_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Raw Post ─────────────────────────────────────────────────────────────────

class RawPostResponse(BaseModel):
    id: UUID
    project_id: UUID
    source: str
    keyword: str
    text: str
    title: Optional[str]
    author: Optional[str]
    url: Optional[str]
    external_id: Optional[str]
    upvotes: int
    comment_count: int
    timestamp: datetime
    processed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RawPostFilter(BaseModel):
    source: Optional[str] = None
    keyword: Optional[str] = None
    processed: Optional[bool] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


# ─── Enriched Post ────────────────────────────────────────────────────────────

class EnrichedPostResponse(BaseModel):
    id: UUID
    raw_post_id: UUID
    project_id: UUID
    clean_text: str
    language: str
    has_pii: bool
    pii_types: List[str]
    drugs: List[str]
    symptoms: List[str]
    conditions: List[str]
    dosages: List[str]
    sentiment: Optional[str]
    sentiment_score: Optional[float]
    entity_sentiment: Dict[str, Any]
    has_safety_signal: bool
    safety_severity: Optional[SignalSeverity]
    safety_signals: List[Any]
    meddra_terms: List[Any]
    relevance_score: float
    is_duplicate: bool
    processed_at: datetime

    model_config = {"from_attributes": True}


class EnrichedPostFilter(BaseModel):
    source: Optional[str] = None
    keyword: Optional[str] = None
    severity: Optional[SignalSeverity] = None
    has_safety_signal: Optional[bool] = None
    drug: Optional[str] = None
    symptom: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    sort_by: str = Field(default="relevance_score", pattern="^(relevance_score|processed_at|safety_severity)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


# ─── Safety Signal ────────────────────────────────────────────────────────────

class SafetySignalResponse(BaseModel):
    id: UUID
    enriched_post_id: UUID
    project_id: UUID
    drug: str
    symptom: str
    severity: SignalSeverity
    meddra_term: Optional[str]
    meddra_code: Optional[str]
    causality: Optional[str]
    confidence: float
    context_window: Optional[str]
    triage_action: TriageAction
    triage_rationale: Optional[str]
    triage_ai_result: Optional[Dict[str, Any]]
    triaged_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class SignalTriageUpdate(BaseModel):
    triage_action: TriageAction
    triage_rationale: Optional[str] = None
    reviewed_by: Optional[str] = "analyst"


# ─── Canvas ───────────────────────────────────────────────────────────────────

class CanvasStateUpdate(BaseModel):
    cards: List[Dict[str, Any]]


class CanvasStateResponse(BaseModel):
    id: UUID
    project_id: UUID
    cards: List[Dict[str, Any]]
    share_id: Optional[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Copilot ──────────────────────────────────────────────────────────────────

class CopilotMessage(BaseModel):
    role: str   # user / assistant
    content: str


class CopilotRequest(BaseModel):
    message: str
    conversation_history: List[CopilotMessage] = []


class CopilotResponse(BaseModel):
    text_response: str
    card: Optional[Dict[str, Any]] = None
    tool_used: Optional[str] = None


# ─── PII Queue ────────────────────────────────────────────────────────────────

class PIIQueueResponse(BaseModel):
    id: UUID
    raw_post_id: UUID
    project_id: UUID
    pii_types: List[str]
    original_text: str
    redacted_text: Optional[str]
    pii_spans: List[Any]
    reviewer_action: PIIReviewAction
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class PIIReviewUpdate(BaseModel):
    reviewer_action: PIIReviewAction
    reviewed_by: Optional[str] = "analyst"


# ─── Dashboard Stats ──────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_posts: int
    signal_counts: Dict[str, int]    # {HIGH: n, MED: n, LOW: n}
    avg_sentiment: float
    pii_queue_depth: int
    mention_volume_7d: List[Dict[str, Any]]    # [{date, count}]
    top_symptoms: List[Dict[str, Any]]         # [{symptom, count, severity}]
    sentiment_by_drug: Dict[str, Any]          # {drug: {positive, neutral, negative}}


# ─── Trends ───────────────────────────────────────────────────────────────────

class SymptomTrend(BaseModel):
    symptom: str
    count: int
    severity: str


class DailyDataPoint(BaseModel):
    date: str
    count: int
    value: Optional[float] = None  # avg sentiment for sentiment series


class EntityDailyVolume(BaseModel):
    entity: str
    daily: List[DailyDataPoint]


class TrendResponse(BaseModel):
    period_days: int
    top_symptoms: List[SymptomTrend]
    symptom_trends: List[EntityDailyVolume]    # per-symptom sparkline data
    sentiment_over_time: List[DailyDataPoint]
    entity_volume: List[DailyDataPoint]        # total drug/condition mentions per day


# ─── Pagination ───────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
